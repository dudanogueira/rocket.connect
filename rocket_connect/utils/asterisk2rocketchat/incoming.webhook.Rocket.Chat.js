/* exported Script */
/* globals console, _, s */

class Script {
  /**
   * @params {object} request
   */
  process_incoming_request({ request }) {
    return {
      content:{
        text: [
            ':no_mobile_phones: *Abandoned Call*',
            ':passport_control: *Queue*: ' + request.content.Queue,
            ':calling: *Caller Number:*: ' + request.content.CallerIDNum,
            ':alarm_clock: *Hold Time*: ' + request.content.HoldTime + 's',
            ':vertical_traffic_light: *Entered at position* ' + request.content.OriginalPosition + '. Abandoned at ' + request.content.Position,
          ].join('\n')
       }
    };
  }
}
