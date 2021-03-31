const venom = require('venom-bot');
venom
    .create(
        'sessionName',
        undefined,
        (statusSession, session) => {
            console.log('Status Session: ', statusSession);
            //return isLogged || notLogged || browserClose || qrReadSuccess || qrReadFail || autocloseCalled || desconnectedMobile || deleteToken
            //Create session wss return "serverClose" case server for close
            console.log('Session name: ', session);
        },
        undefined
    )
    .then((client) => {
        start(client);
        client.onStateChange(state => {
            console.log("STATE CHANGE: ", state)
        });
    })
    .catch((erro) => {
        console.log(erro);
    });


function start(client) {
    client.onMessage((message) => {
        if (message.body === 'Hi' && message.isGroupMsg === false) {
            client
                .sendText(message.from, 'Welcome Venom 🕷')
                .then((result) => {
                    console.log('Result: ', result); //return object success
                })
                .catch((erro) => {
                    console.error('Error when sending: ', erro); //return object error
                });
        }
    });
}