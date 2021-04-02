// Supports ES6
// import { create, Whatsapp } from 'venom-bot';
const venom = require('venom-bot');
const axios = require('axios');
const fs = require('fs');

async function init_venom(session, hook, handle_start) {
  venom
    .create(
      //session
      session,
      //
      // handle qr code
      //
      (base64Qrimg, asciiQR, attempts, urlCode) => {
        handle_qr_code(base64Qrimg, asciiQR, attempts, urlCode, session, hook);
      },
      //
      // handle status session
      //
      (statusSession, session) => {

        handle_status_session(statusSession, session, hook);

      },
      //
      // instance configs
      //
      {
        autoClose: 5000,
        headless: false, useChrome: false
      },
      //
      // Browser Instance
      //
      (browser, waPage) => {
        handle_browser_instance(browser, waPage)
      }
    )
    .then((client) => {
      handle_start(client, hook);
      // session management

      

      // function to detect incoming call
      client.onIncomingCall(async (call) => {
        console.log(call);
        client.sendText(call.peerJid, "Sorry, I still can't answer calls");
      });

    })
    .catch((erro) => {
      console.log(erro);
    });
}

function start(client, hook) {
  // new message
  client.onMessage((message) => {
    //on message, send to hook
    if (message.isGroupMsg === false) {
      axios.post(hook, message).then(
        ok => { console.log('ok, ', ok) },
        err => { console.log('err', err) }
      );
      console.log(message)
      // client
      //   .sendText(message.from, 'Welcome Venom 🕷')
      //   .then((result) => {
      //     console.log('Result: ', result); //return object success
      //   })
      //   .catch((erro) => {
      //     console.error('Error when sending: ', erro); //return object error
      //   });
    }
  });
  // status change
  client.onStateChange((state) => {
    console.log('State changed: ', state);
  });


}

function handle_qr_code(base64Qrimg, asciiQR, attempts, urlCode, session_name, hook) {
  console.log('Number of attempts to read the qrcode: ', attempts);
  console.log('sending qr code to hook: ', hook)
  //
  // send qr to hood
  //
  axios.post(
    hook,
    {
      "session": session_name,
      "context": "admin",
      "topic": "qrcode",
      "attempt": attempts,
      "base64Qrimg": base64Qrimg,
    }
  ).then(function (response) {
    console.log("qrcode sent to hook");
  }).catch(function (error) {
    console.log("error sending qrc to hook: ", error);
  });
}

function handle_status_session(statusSession, session, hook) {
  axios.post(
    hook,
    {
      "session": session,
      "context": "admin",
      "topic": "status_session",
      "message": statusSession
    }
  ).then(function (response) {
    console.log(`session status sent to hook ${hook}: ${statusSession}`);
  })
    .catch(function (error) {
      console.log(`error session status sent to hook ${hook}: ${statusSession}`);
    });
}

function handle_browser_instance(browser, waPage) {
  console.log("Browser PID:", browser.process().pid);
  console.log("Browser:", browser);
  console.log("waPage:", waPage);
  waPage.screenshot({ path: session + '-' + 'screenshot.png' });
}



//init_venom("instancia1", "http://127.0.0.1:8000/connector/ccf9bed0-34e4-4367-9f25-e469bda54c8a", start);
await init_venom("instancia2", "http://127.0.0.1:8000/connector/e62f9f19-becf-4f29-84d2-ef0ecb36e269", start);
