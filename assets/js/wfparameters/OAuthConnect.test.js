import React from 'react'
import OAuthConnect  from './OAuthConnect'
import { mount, ReactWrapper } from 'enzyme'
import { jsonResponseMock } from '../utils'
import { store,  getCurrentUserAction, disconnectCurrentUserAction } from '../workflow-reducer';
jest.mock('../workflow-reducer');

describe('OAuthConnect', () => {
  const wrapper = (extraProps) => {
    return mount(
      <OAuthConnect
        paramIdName={'x'}
        deleteSecret={jest.fn(() => Promise.resolve(null))}
        paramId={321}
        secretName={'a secret'}
        {...extraProps}
        />
    )
  }

  it('matches snapshot', () => {
    const w = wrapper({})
    expect(w).toMatchSnapshot()
  })

  it('renders without a secretName', () => {
    const w = wrapper({ secretName: null })
    expect(w.find('button.connect')).toHaveLength(1)
  })

  it('disconnects', () => {
    const w = wrapper({ secretName: 'foo@example.org' })
    w.find('button.disconnect').simulate('click')
    expect(w.prop('deleteSecret')).toHaveBeenCalledWith('x')
  })
})
