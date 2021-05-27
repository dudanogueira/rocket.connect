// Supports ES6
const venom = require('venom-bot');
const axios = require('axios').default;

//Create your webhook here: https://webhook.site/
const WEBHOOK_ADDRESS = 'http://django:8000/connector/VENOM_CONNECTOR/'

const express = require('express');
const app = express();
app.use(express.json());
const PORT = 8092;


async function fire(data) {
    return await axios.post(WEBHOOK_ADDRESS, data)
}

function wh(event, data) {
    const ts = Date.now();
    return fire({
        ts,
        event,
        data
    })
}



venom
    .create(
        //session
        'sessionName', //Pass the name of the client you want to start the bot
        //catchQR
        (base64Qrimg, asciiQR, attempts, urlCode) => {
            wh('OnQRCode', {
                "base64Qrimg": base64Qrimg,
                "attempts": attempts,
                "urlCode": urlCode
            })
        },
        // statusFind
        (statusSession, session) => {
            wh('onStateChanged', statusSession)
        },
        // options
        {
            folderNameToken: 'tokens', //folder name when saving tokens
            mkdirFolderToken: '', //folder directory tokens, just inside the venom folder, example:  { mkdirFolderToken: '/node_modules', } //will save the tokens folder in the node_modules directory
            headless: true, // Headless chrome
            devtools: false, // Open devtools by default
            useChrome: true, // If false will use Chromium instance
            debug: false, // Opens a debug session
            logQR: false, // Logs QR automatically in terminal
            browserWS: 'http://browser:3000', // If u want to use browserWSEndpoint
            browserArgs: [''], //Original parameters  ---Parameters to be added into the chrome browser instance
            puppeteerOptions: {}, // Will be passed to puppeteer.launch
            disableSpins: true, // Will disable Spinnies animation, useful for containers (docker) for a better log
            disableWelcome: true, // Will disable the welcoming message which appears in the beginning
            updatesLog: true, // Logs info updates automatically in terminal
            autoClose: 0, // Automatically closes the venom-bot only when scanning the QR code (default 60 seconds, if you want to turn it off, assign 0 or false)
            createPathFileToken: true, //creates a folder when inserting an object in the client's browser, to work it is necessary to pass the parameters in the function create browserSessionToken
        },
        {}
    )
    .then((client) => start(client))
    .catch((erro) => {
        console.log(erro);
    });

function start(client) {
    client.onMessage(message => {
        wh('onMessage', message)
    })
    // Listen to state changes
    client.onStateChange(message => hw('onStateChange', message));
    //   client.onMessage((message) => {
    //     if (message.body === 'Hi' && message.isGroupMsg === false) {
    //       client
    //         .sendText(message.from, 'Welcome Venom 🕷')
    //         .then((result) => {
    //           console.log('Result: ', result); //return object success
    //         })
    //         .catch((erro) => {
    //           console.error('Error when sending: ', erro); //return object error
    //         });
    //     }
    //   });
    app.post('/sendText', function (req, res) {
        console.log(req.body);
        client
            .sendText(req.body.args.to, req.body.args.content)
            .then((result) => {
                res.send(result);
            })
            .catch((erro) => {
                res.send(erro);
            });
    });

    app.listen(PORT, function () {
        console.log(`\n• Listening on port ${PORT}!`);

    });




}
