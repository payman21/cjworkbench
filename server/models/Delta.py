# Delta
# A single change to state of a workflow
# You can also think of this as a "command." Contains a specification of what
# actually happened.
import json
from typing import Any, Optional
from django.core.serializers.json import DjangoJSONEncoder
from django.db import connection, models
import django.utils
from polymorphic.models import PolymorphicModel
from cjworkbench.sync import database_sync_to_async
from server import rabbitmq, websockets
from server.serializers import WfModuleSerializer


def _prepare_json(data: Any) -> Any:
    """Convert `data` into a simple, JSON-ready dict."""
    return json.loads(json.dumps(data, cls=DjangoJSONEncoder))


# Base class of a single undoable/redoable action
# Derived classes implement the actual mutations on the database
# (via polymorphic forward()/backward())
# To derive a command from Delta:
#
#   - implement @classmethod amend_create_kwargs() -- a database-sync method.
#   - implement forward_impl() and backward_impl() -- database-sync methods.
#
# When creating a Delta, the two commands will be called in the same atomic
# transaction.
class Delta(PolymorphicModel):
    class Meta:
        # OMG this bug ate so many hours...
        # https://github.com/django-polymorphic/django-polymorphic/issues/229
        base_manager_name = 'base_objects'

    # These fields must be set by any child classes, when instantiating
    workflow = models.ForeignKey('Workflow', related_name='deltas',
                                 on_delete=models.CASCADE)

    # Next and previous Deltas on this workflow, a linked list.
    prev_delta = models.OneToOneField('self', related_name='next_delta',
                                      null=True, default=None,
                                      on_delete=models.CASCADE)

    datetime = models.DateTimeField('datetime',
                                    default=django.utils.timezone.now)

    @database_sync_to_async
    def _call_forward_and_load_ws_data(self):
        with self.workflow.cooperative_lock():
            self.forward_impl()

            # Point workflow to us
            self.workflow.last_delta = self
            self.workflow.save(update_fields=['last_delta_id'])

            return self.load_ws_data()

    @database_sync_to_async
    def _call_backward_and_load_ws_data(self):
        with self.workflow.cooperative_lock():
            self.backward_impl()

            # Point workflow to previous delta
            # Only update prev_delta_id: other columns may have been edited in
            # backward_impl().
            self.workflow.last_delta = self.prev_delta
            self.workflow.save(update_fields=['last_delta_id'])

            return self.load_ws_data()

    async def forward(self):
        """Call forward_impl() with workflow.cooperative_lock()."""
        ws_data = await self._call_forward_and_load_ws_data()
        await self.ws_notify(ws_data)
        await self.schedule_execute_if_needed()

    async def backward(self):
        """Call backward_impl() with workflow.cooperative_lock()."""
        ws_data = await self._call_backward_and_load_ws_data()
        await self.ws_notify(ws_data)
        await self.schedule_execute_if_needed()

    async def ws_notify(self, ws_data):
        """
        Notify WebSocket clients that we just undid or redid.

        This must be called within the same Workflow.cooperative_lock() that
        triggered the change in the first place.
        """
        await websockets.ws_client_send_delta_async(self.workflow_id, ws_data)

    def load_ws_data(self):
        workflow = self.workflow
        data = {
            'updateWorkflow': {
                'name': workflow.name,
                'public': workflow.public,
                'last_update': workflow.last_update().isoformat(),
            },
            'updateWfModules': {}
        }

        if hasattr(self, '_changed_wf_module_versions'):
            for id, delta_id in self._changed_wf_module_versions:
                data['updateWfModules'][str(id)] = {
                    'last_relevant_delta_id': delta_id,
                    'quick_fixes': [],
                    'output_columns': [],
                    'output_error': '',
                    'output_status': 'busy',
                    'output_n_rows': 0,
                }

        if hasattr(self, 'wf_module'):
            if self.wf_module.is_deleted or self.wf_module.tab.is_deleted:
                # When we did or undid this command, we removed the
                # WfModule from the Workflow.
                data['clearWfModuleIds'] = [self.wf_module_id]
            else:
                # Serialize _everything_, including params
                #
                # TODO consider serializing only what's changed, so when Alice
                # changes 'has_header' it doesn't overwrite Bob's 'url' while
                # he's editing it.
                wf_module_data = WfModuleSerializer(self.wf_module).data

                data['updateWfModules'][str(self.wf_module_id)] = \
                    _prepare_json(wf_module_data)

        return data

    async def schedule_execute_if_needed(self) -> None:
        """
        If any WfModule output may change, schedule a render over RabbitMQ.
        """
        if hasattr(self, '_changed_wf_module_versions'):
            if len(self._changed_wf_module_versions):
                await rabbitmq.queue_render(self.workflow.id,
                                            self.workflow.last_delta_id)

    @classmethod
    async def create(cls, *, workflow, **kwargs) -> None:
        """Create the given Delta and run .forward().

        Keyword arguments vary by cls, but `workflow` is always required.

        If `amend_create_kwargs()` returns `None`, no-op.

        Example:

            delta = await ChangeWfModuleNotesCommand.create(
                workflow=wf_module.workflow,
                # ... other kwargs
            )
            # now delta has been applied and committed to the database, and
            # websockets users have been notified.
        """
        delta, ws_data = await cls._first_forward_and_save_returning_ws_data(
            workflow=workflow,
            **kwargs
        )

        if delta:
            await delta.ws_notify(ws_data)
            await delta.schedule_execute_if_needed()

        return delta

    @classmethod
    def amend_create_kwargs(cls, **kwargs):
        """
        Look up additional objects.create() kwargs from the database.

        Delta creation can depend upon values already in the database. The
        delta may calculate those values itself.

        Return `None` to abort creating the Delta altogether.

        Example:

            @classmethod
            def amend_create_kwargs(cls, *, workflow, **kwargs):
                return {**kwargs, 'workflow': workflow, 'old_value': ... }
        """
        return kwargs

    @classmethod
    @database_sync_to_async
    def _first_forward_and_save_returning_ws_data(cls, **kwargs):
        """
        Create and execute command, returning `(Delta, WebSockets data)`.

        If `amend_create_kwargs()` returns `None`, return `(None, None)` here.

        All this, in a cooperative lock.
        """
        workflow = kwargs['workflow']
        with workflow.cooperative_lock():
            create_kwargs = cls.amend_create_kwargs(**kwargs)
            if not create_kwargs:
                return (None, None)

            # Lookup unapplied deltas to delete. That's the head of the linked
            # list that comes _after_ `workflow.last_delta`.
            orphan_delta: Optional[Delta] = Delta.objects \
                .filter(prev_delta_id=workflow.last_delta_id) \
                .first()
            if orphan_delta:
                orphan_delta.delete_with_successors()

            delta = cls.objects.create(prev_delta_id=workflow.last_delta_id,
                                       **create_kwargs)
            delta.forward_impl()

            if orphan_delta:
                # We just deleted deltas; now we can garbage-collect Tabs and
                # WfModules that are soft-deleted and have no deltas referring
                # to them.
                workflow.delete_orphan_soft_deleted_models()
                pass

            # Point workflow to us
            workflow.last_delta = delta
            workflow.save(update_fields=['last_delta_id'])

            return (delta, delta.load_ws_data())

    def delete_with_successors(self):
        """
        Delete all Deltas starting with this one.

        Do it in SQL, not code: there can be thousands, and Django's models are
        resource-intensive. (Also, recursion is out of the question, in these
        quantities.)

        Assumes a Delta with a higher ID is a successor.

        Consider calling `workflow.delete_orphan_soft_deleted_models()` after
        calling this method: it may leave behind Tab and WfModule objects that
        nothing refers to, if they previously had `.is_deleted == True`.
        """
        # Oh, Did You Know: django-polymorphic does not have a "delete"
        # feature?
        command_relations = [
            rel
            for rel in Delta._meta.related_objects
            if rel.parent_link
        ]
        with_clauses = [
            f"""
            delete_{i} AS (
                DELETE FROM {rel.related_model._meta.db_table} t
                WHERE t.{rel.get_joining_columns()[0][1]} IN (
                    SELECT id FROM to_delete
                )
            )
            """
            for i, rel in enumerate(command_relations)
        ]
        with connection.cursor() as cursor:
            cursor.execute(f"""
            WITH
            to_delete AS (
                SELECT id
                FROM {Delta._meta.db_table}
                WHERE workflow_id = {int(self.workflow_id)}
                  AND id >= {int(self.id)}
            ),
            {', '.join(with_clauses)}
            DELETE FROM {Delta._meta.db_table}
            WHERE id IN (SELECT id FROM to_delete)
            """)

    @property
    def command_description(self):
        # can be called from Django admin when deleting a wf
        return "Base Delta object"

    def __str__(self):
        return str(self.datetime) + ' ' + self.command_description
