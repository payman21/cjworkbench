/* global describe, it, jest, expect */
import React from 'react'
import ColumnContextMenu from './ColumnContextMenu'
import { shallow } from 'enzyme'
import { sortDirectionNone, sortDirectionAsc, sortDirectionDesc } from './SortFromTable'
import { tick } from './test-utils'

describe('ColumnContextMenu', () => {
  function mountMenu (sortDirection, setSortDirection) {
    return shallow(
      <ColumnContextMenu
        sortDirection={sortDirection}
        setSortDirection={setSortDirection}
      />
    )
  }

  it('should match snapshot', () => {
    let wrapper = mountMenu(sortDirectionNone, jest.fn())
    expect(wrapper).toMatchSnapshot() // stores file which represents tree of component
  })

  // only checking the call to set the sort direction, not the actual sort
  it('should call setSortDirection', async () => {
    const fn = jest.fn()
    const wrapper = mountMenu(sortDirectionNone, fn)

    wrapper.find('DropdownItem.sort-ascending').simulate('click')
    expect(fn).toHaveBeenCalledWith(sortDirectionAsc)

    wrapper.find('DropdownItem.sort-descending').simulate('click')
    expect(fn).toHaveBeenCalledWith(sortDirectionDesc)
  })
})
