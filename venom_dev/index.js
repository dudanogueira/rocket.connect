// Supports ES6
// import { create, Whatsapp } from 'venom-bot';
const venom = require('venom-bot');
const axios = require('axios');

function init_venom(session_name, hook, handle_function) {
  venom
    .create(
      //session
      session_name, //Pass the name of the client you want to start the bot
      //catchQR
      (base64Qrimg, asciiQR, attempts, urlCode) => {
        console.log('Number of attempts to read the qrcode: ', attempts);
        console.log('sending qr code to hook: ', hook)
        axios.post(
          hook,
          {
            "session": session_name,
            "context": "management",
            "topic": "qrcode",
            "attemps": attempts,
            "base64Qrimg": base64Qrimg,
          }
        ).then(function (response) {
          console.log("qrcode sent to hook");
        })
        .catch(function (error) {
          console.log("error sending qrc to hook");
        });
      },
      (statusSession, session) => {
        // send status session
        axios.post(
          hook,
          {
            "session": session_name,
            "context": "management",
            "topic": "status_session",
            "message": statusSession
          }
        ).then(function (response) {
          console.log("qrcode sent to hook");
        })
        .catch(function (error) {
          console.log("error sending qrc to hook");
        });

      },
      undefined
    )
    .then((client) => {
      handle_function(client, hook);
    })
    .catch((erro) => {
      console.log(erro);
    });
}

function start(client, hook) {
  client.onMessage((message) => {
    axios.post();
    // on message, send to hook
    // if (message.isGroupMsg === false) {
    //   client
    //     .sendText(message.from, 'Welcome Venom 🕷')
    //     .then((result) => {
    //       console.log('Result: ', result); //return object success
    //     })
    //     .catch((erro) => {
    //       console.error('Error when sending: ', erro); //return object error
    //     });
    // }
  });
}

init_venom("instancia1", "http://127.0.0.1:8000/connector/ccf9bed0-34e4-4367-9f25-e469bda54c8a", start);
init_venom("instancia2", "http://127.0.0.1:8000/connector/e62f9f19-becf-4f29-84d2-ef0ecb36e269", start);
