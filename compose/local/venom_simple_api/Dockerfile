FROM node:15-alpine

# Create app directory
WORKDIR /usr/src/app

# Install app dependencies
# A wildcard is used to ensure both package.json AND package-lock.json are copied
# where available (npm@5+)
COPY package*.json ./

RUN npm install --save

# Bundle app source
ADD . /usr/src/app

EXPOSE 8096
CMD [ "node", "index.js" ]
