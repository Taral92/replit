FROM node:20-alpine

WORKDIR /app

# Install native build tools for node-pty and bash for the terminal
RUN apk add --no-cache python3 make g++ bash

# Copy package files and install dependencies
COPY package*.json ./
RUN npm install

# Copy source code and build
COPY . .
RUN npm run build

EXPOSE 3000

CMD ["npm", "start"]
