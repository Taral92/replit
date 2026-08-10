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

io.on("connection", (socket) => {
    console.log(`[Socket] User connected: ${socket.id}`);

    // Listen for any incoming events
    socket.onAny((eventName, ...args) => {
        console.log(`[Socket] Received event: ${eventName}`, args);
        
        // ECHO back to prove communication
        socket.emit("echo", {
            event: eventName,
            data: args
        });
    });

    socket.on("disconnect", () => {
        console.log(`[Socket] User disconnected: ${socket.id}`);
    });
});

const PORT = process.env.PORT || 3000;
httpServer.listen(PORT, () => {
    console.log(`Runner Service listening on port ${PORT}`);
});
