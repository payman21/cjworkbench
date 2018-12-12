import { addModuleAction, setWfModuleParamsAction, setSelectedWfModuleAction } from '../workflow-reducer'

/**
 * Module param-building functions per id_name.
 *
 * Each function has the signature (oldParams, params), and it should
 * return new params or null.
 *
 * `oldParams` will be `null` if this is a new module.
 *
 * Watch out: these param builders are NOT all used in the same way! For
 * example, editcells' "params" is used to add an _edit_, not overwrite an
 * "edits" param. In effect, this is a bunch of functions with completely
 * different purposes but with the same calling convention (kinda like Redux
 * reducers.) Most are used in the column drop-down menu. TODO move the others
 * elsewhere.
 */
export const moduleParamsBuilders = {
  'selectcolumns': buildSelectColumnsParams,
  'duplicate-column': genericAddColumn('colnames'),
  'filter': genericSetColumn('column'),
  'editcells': buildEditCellsParams,
  'rename-columns': buildRenameColumnsParams,
  'reorder-columns': buildReorderColumnsParams,
  'sort-from-table': genericSetColumn('column'),
  'extract-numbers': genericAddColumn('colnames'),
  'clean-text': genericAddColumn('colnames'),
  'convert-date': genericAddColumn('colnames'),
  'convert-text': genericAddColumn('colnames')
}

function moduleExists (state, moduleIdName) {
  const { modules } = state
  for (const key in modules) {
    if (modules[key].id_name === moduleIdName) return true
  }
  return false
}

function wfModuleParams (wfModule) {
  const ret = {}
  for (const param of wfModule.parameter_vals) {
    ret[param.parameter_spec.id_name] = param.value
  }
  return ret
}

/**
 * Return { id, params, isNext } of _this_ WfModule or the one _after_ it, matching moduleIdName.
 *
 * Return `null` if this or the next WfModule does not match moduleIdName.
 */
function findWfModuleWithIds (state, focusWfModuleId, moduleIdName) {
  const { tabs, wfModules, modules } = state

  let moduleId = null
  for (const key in modules) {
    if (modules[key].id_name === moduleIdName) {
      moduleId = +key
      break
    }
  }
  if (moduleId === null) throw new Error(`Cannot find module '${moduleIdName}'`)

  const wfModule = wfModules[String(focusWfModuleId)]
  const tabId = wfModule.tab_id
  const tab = tabs[String(tabId)]

  // validIdsOrNulls: [ 2, null, null, 65 ] means indices 0 and 3 are for
  // desired module (and have wfModuleIds 2 and 64), 1 and 2 aren't for
  // desired module
  const validIdsOrNulls = tab.wf_module_ids
    .map(id => (wfModules[String(id)].module_version || {}).module === moduleId ? id : null)

  const focusIndex = tab.wf_module_ids.indexOf(focusWfModuleId)
  if (focusIndex === -1) return null

  // Are we already focused on a valid WfModule?
  const atFocusIndex = validIdsOrNulls[focusIndex]
  if (atFocusIndex !== null) {
    const wfModule = wfModules[String(atFocusIndex)]
    return {
      id: atFocusIndex,
      params: wfModuleParams(wfModule),
      isNext: false
    }
  }

  // Is the _next_ wfModule valid? If so, return that
  const nextIndex = focusIndex + 1
  const atNextIndex = nextIndex >= validIdsOrNulls.length ? null : validIdsOrNulls[nextIndex]
  if (atNextIndex !== null) {
    const wfModule = wfModules[String(atNextIndex)]
    return {
      id: atNextIndex,
      params: wfModuleParams(wfModule),
      isNext: true
    }
  }

  // Nope, no target module with moduleIdName where we need it
  return null
}

function ensureSelectedWfModuleId (dispatch, state, wfModuleId) {
  const { wfModules, tabs } = state

  const wfModule = wfModules[String(wfModuleId)]
  const tabId = wfModule.tab_id
  const tab = tabs[String(tabId)]
  const current = tab.selected_wf_module_position
  const wanted = tab.wf_module_ids.indexOf(wfModuleId)

  if (wanted !== -1 && wanted !== current) {
    dispatch(setSelectedWfModuleAction(wanted))
  }
}

/**
 * Adds or edits a module, given `wfModuleId` as the selected table.
 *
 * This is a reducer action that delegates to `addModuleAction`, `setSelectedWfModuleAction` and `
 */
export function updateTableAction (wfModuleId, idName, forceNewModule, params) {
  return (dispatch, getState) => {
    const state = getState()

    if (!moduleExists(state, idName)) {
      window.alert("Module '" + idName + "' not imported.")
      return
    }

    const existingModule = forceNewModule ? null : findWfModuleWithIds(state, wfModuleId, idName)
    const newParams = moduleParamsBuilders[idName](existingModule ? existingModule.params : null, params)

    if (existingModule && !forceNewModule) {
      ensureSelectedWfModuleId(dispatch, state, existingModule.id) // before state's existingModule changes

      if (newParams) dispatch(setWfModuleParamsAction(existingModule.id, newParams))
    } else {
      dispatch(addModuleAction(idName, { afterWfModuleId: wfModuleId }, newParams))
    }
  }
}

function buildSelectColumnsParams (oldParams, params) {
  if (Object.keys(params).length === 0) {
    // A bit of a hack: if we call this with no params, we're just adding
    // an empty select-columns module with default params.
    return {}
  }

  const colnames = oldParams ? oldParams.colnames.split(',').filter(s => !!s) : []
  const keep = params ? params.drop_or_keep == 1 : true
  const oldKeep = oldParams ? oldParams.drop_or_keep == 1 : keep
  const keepIdx = keep ? 1 : 0
  const oldKeepIdx = oldKeep ? 1 : 0
  const colname = params.columnKey // may be undefined

  if (colnames.length === 0) {
    // Adding a new module, or resetting an empty one
    return { colnames: colname, drop_or_keep: keepIdx }
  } else {
    const idx = colnames.indexOf(colname)

    if (oldKeep) {
      // Existing module is "keep"
      if (keep) {
        throw new Error('Unhandled case: trying to keep in a keep module')
        return null
      } else {
        // We want to drop
        if (idx === -1) {
          return null // the keep module doesn't include colname: it's already dropped
        } else {
          colnames.splice(idx, 1)
          return { colnames: colnames.join(','), drop_or_keep: oldKeepIdx }
        }
      }
    } else {
      // Existing module is "drop"
      if (keep) {
        throw new Error('Unhandled case: trying to keep in a remove module')
        return null
      } else {
        // We want to drop another one
        if (idx === -1) {
          colnames.push(colname)
          return { colnames: colnames.join(','), drop_or_keep: oldKeepIdx }
        } else {
          return null // the drop module is already dropping colname
        }
      }
    }

    if (keep === oldKeep) {
      if (keep && idx === -1) {
        colnames.push(params.columnKey)
        return { colnames, drop_or_keep: keepIdx }
      } else if (!keep && idx !== -1) {
      } else {
        return null
      }
    } else {
      console.warn('Unimplemented drop/keep logic', oldKeep, keep, colnames, colname)
      return null
    }
  }
}

function buildEditCellsParams (oldParams, params) {
  const edits = (oldParams && oldParams.celledits) ? JSON.parse(oldParams.celledits) : []
  const edit = params

  // Remove the previous edit to the same cell
  const idx = edits.findIndex(({ row, col }) => row === edit.row && col === edit.col)

  if (idx === -1) {
    edits.push(edit)
    return { celledits: JSON.stringify(edits) }
  } else if (edits[idx].value !== edit.value) {
    edits.splice(idx, 1, edit)
    return { celledits: JSON.stringify(edits) }
  } else {
    return null
  }
}

function genericSetColumn (key) {
  return (oldParams, params) => {
    const newParams = { ...params }
    const colname = newParams.columnKey
    if (newParams.hasOwnProperty('columnKey')) {
      delete newParams.columnKey
      newParams[key] = colname
    }
    return newParamsUnlessNoChange(oldParams, newParams)
  }
}

function newParamsUnlessNoChange (oldParams, newParams) {
  if (!oldParams) return newParams
  for (const key in oldParams) {
    if (oldParams[key] !== newParams[key]) {
      return newParams
    }
  }
  return null
}

function genericAddColumn (key) {
  return (oldParams, params) => {
    const colnames = oldParams ? oldParams[key].split(',').filter(s => !!s) : []
    if (!params.hasOwnProperty('columnKey'))  throw new Error('Expected "columnKey" column to add')
    const colname = params.columnKey

    if (!colname) throw new Error('Unexpected params: ' + JSON.stringify(params))

    if (colnames.includes(colname)) {
      return null
    } else {
      const newParams = { ...params }
      const colname = newParams.columnKey
      delete newParams.columnKey
      newParams[key] = [ ...colnames, colname ].join(',')

      return newParamsUnlessNoChange(oldParams, newParams)
    }
  }
}

function buildRenameColumnsParams (oldParams, params) {
  // renameInfo format: {prevName: <current column name in table>, newName: <new name>}
  const entries = (oldParams && oldParams['rename-entries']) ? JSON.parse(oldParams['rename-entries']) : {}
  const { prevName, newName } = params

  if (entries[prevName] === newName) {
    return null
  } else {
    entries[prevName] = newName
    return { 'rename-entries': JSON.stringify(entries) }
  }
}

function buildReorderColumnsParams (oldParams, params) {
  // Yes, yes, this is half-broken -- https://www.pivotaltracker.com/story/show/162592381
  const historyEntries = (oldParams && oldParams['reorder-history']) ? JSON.parse(oldParams['reorder-history']) : []

  let { column, to, from } = params

  // User must drag two spaces to indicate moving one column right (because drop = place before this column)
  // So to prevent all other code from having to deal with this forever, decrement the index here
  if (to > from) {
    to -= 1
  }

  historyEntries.push({ column, to, from })
  return { 'reorder-history': JSON.stringify(historyEntries) }
}
