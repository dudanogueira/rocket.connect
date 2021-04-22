FROM node:current-alpine

# Create app directory
WORKDIR /usr/src/app

# Install app dependencies
RUN apk add --no-cache python3 alpine-sdk

# A wildcard is used to ensure both package.json AND package-lock.json are copied
# where available (npm@5+)
COPY package*.json ./

# Uncomment the next line to use this Dockerfile on your own app
#run npm install

RUN npm install --only=dev --ignore-scripts
RUN npm rebuild --verbose sharp

# Copy the session data over to the container
# Bundle app source
COPY . .

EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=20s --start-period=60s \
    CMD node healthcheck.js

CMD ["npm", "run", "start"]
