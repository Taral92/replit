import express from "express";
import { createServer } from "http";
import { Server } from "socket.io";
import cors from "cors";

const app = express();
app.use(cors());

const httpServer = createServer(app);
const io = new Server(httpServer, {
    cors: {
        origin: "*",
        methods: ["GET", "POST"]
    }
});

// A basic health check endpoint for Kubernetes
app.get("/health", (req, res) => {
    res.send("Runner is healthy");
});

import * as pty from "node-pty";

io.on("connection", (socket) => {
    console.log(`[Socket] User connected: ${socket.id}`);

    // Spawn a new pseudo-terminal running bash
    const shell = process.env.SHELL || "/bin/bash";
    const ptyProcess = pty.spawn(shell, [], {
        name: "xterm-color",
        cols: 80,
        rows: 24,
        cwd: "/app",
        env: process.env
    });

    // 1. Terminal -> Browser
    // Whenever the bash process outputs data, send it to the client
    ptyProcess.onData((data) => {
        socket.emit("terminal:data", data);
    });

    // 2. Browser -> Terminal
    // Whenever the user types a key in the browser, write it to the bash process
    socket.on("terminal:write", (data) => {
        ptyProcess.write(data);
    });

    // Optional: Handle terminal resizing
    socket.on("terminal:resize", ({ cols, rows }) => {
        ptyProcess.resize(cols, rows);
    });

    socket.on("disconnect", () => {
        console.log(`[Socket] User disconnected: ${socket.id}`);
        // Clean up the terminal process
        ptyProcess.kill();
    });
});

const PORT = process.env.PORT || 3000;
httpServer.listen(PORT, () => {
    console.log(`Runner Service listening on port ${PORT}`);
});
