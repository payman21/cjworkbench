from unittest.mock import patch
from server.models import Workflow
from server.models.commands import ChangeWorkflowTitleCommand
from server.tests.utils import DbTestCase


async def async_noop(*args, **kwargs):
    pass


@patch('server.rabbitmq.queue_render', async_noop)
@patch('server.models.Delta.ws_notify', async_noop)
class ChangeWorkflowTitleCommandTests(DbTestCase):
    def test_change_title(self):
        workflow = Workflow.create_and_init(name='title1')

        # Change back to second title, see if it saved
        cmd = self.run_with_async_db(ChangeWorkflowTitleCommand.create(
            workflow=workflow,
            new_value='title2'
        ))
        self.assertEqual(workflow.name, 'title2')  # test var change
        workflow.refresh_from_db()
        self.assertEqual(workflow.name, 'title2')  # test DB change

        # undo
        self.run_with_async_db(cmd.backward())
        self.assertEqual(workflow.name, 'title1')  # test var change
        workflow.refresh_from_db()
        self.assertEqual(workflow.name, 'title1')  # test DB change

        # redo
        self.run_with_async_db(cmd.forward())
        self.assertEqual(workflow.name, 'title2')
        workflow.refresh_from_db()
        self.assertEqual(workflow.name, 'title2')
