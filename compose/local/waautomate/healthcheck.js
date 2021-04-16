var url = 'http://localhost:8002/healthCheck';


const http = require('http')

const data = JSON.stringify({})

const options = {
    host: "localhost",
    port: "8002",
    path: "/healthCheck",
    method: 'POST',
    headers: {
        'Content-Type': 'application/json',
        'Content-Length': data.length
    }
}

const req = http.request(options, res => {
    if (res.statusCode == 200) {
        // api is UP
        let body = [];
        res.on('data', (chunk) => {
            body.push(chunk);
        }).on('end', () => {
            body = Buffer.concat(body).toString();
            // get json
            j = JSON.parse(body)
            // response was ok
            if (j.success){
                // todo: check if isonline
                process.exit(0);
            }else{
                process.exit(1);
            }
        });

    } else {
        // no
        process.exit(1);
    }


})

req.on('error', error => {
    console.log("ERROR");
    process.exit(1);
})

req.write(data)
req.end()
