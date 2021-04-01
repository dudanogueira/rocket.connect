// Supports ES6
// import { create, Whatsapp } from 'venom-bot';
const venom = require('venom-bot');
const axios = require('axios');
const fs = require('fs');

function init_venom(session_name, hook, handle_function) {
  venom
    .create(
      //session
      session_name, //Pass the name of the client you want to start the bot
      //
      // pass qr code to hook
      //
      (base64Qrimg, asciiQR, attempts, urlCode) => {
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
        })
          .catch(function (error) {
            console.log("error sending qrc to hook");
          });

      },
      //
      // send status to hook
      //
      (statusSession, session) => {
        // send status session
        axios.post(
          hook,
          {
            "session": session_name,
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

      },
      //
      //
      //
      {
        autoClose: false,
        headless: false, useChrome: false
      }
    )
    .then((client) => {
      handle_function(client, hook);
      // session management
      client.onStateChange((state) => {
        console.log('State changed: ', state);
        // force whatsapp take over
        if ('CONFLICT'.includes(state)) client.useHere();
        // detect disconnect on whatsapp
        if ('UNPAIRED'.includes(state)) console.log('logout');
        // disconected
        if ('OPENING'.includes(state)) {
          // remove the token
          token_path = `tokens/${session_name}.data.json`
          console.log('unlinking ', token_path)
          //fs.unlink(`tokens/${session_name}.data.json`, (err => console.log(err)))
          console.log('REOPENING');
          // reinitiate venom
          //client.close();
          //init_venom(session_name, hook, handle_function);
          //client.restartService();
        }

      });

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
}

//init_venom("instancia1", "http://127.0.0.1:8000/connector/ccf9bed0-34e4-4367-9f25-e469bda54c8a", start);
init_venom("instancia2", "http://127.0.0.1:8000/connector/e62f9f19-becf-4f29-84d2-ef0ecb36e269", start);
