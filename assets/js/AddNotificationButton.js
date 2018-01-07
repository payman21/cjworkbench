import React from 'react';
import { DragSource } from 'react-dnd';

const spec = {
  beginDrag(props, monitor, component) {
    return {
      index: false,
      id: props.id,
      insert: true,
    }
  }
}

function collect(connect, monitor) {
  return {
    connectDragSource: connect.dragSource(),
    isDragging: monitor.isDragging()
  }
}

class AddNotificationButton extends React.Component {
  constructor(props) {
    super(props);
  }

  render() {
    return this.props.connectDragSource(
      <div className='card' style={{'borderRadius': 0, 'border': 0}}>
        <div className='second-level t-vl-gray d-flex'>
          <div className='d-flex flex-row align-items-center'>

            <div className='ml-icon-container'>
              <div className="icon-notification ml-icon"></div>
            </div>

            <div>
              <div className='content-5 ml-module-name'>Add data alert</div>
            </div>
          </div>

          <div className='ml-handle'>
            <div className='icon-grip'></div>
          </div>
        </div>
      </div>
    )
  }

}

export default DragSource('notification', spec, collect)(AddNotificationButton)
