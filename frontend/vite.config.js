import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// The browser calls /api on the address it loaded the page from, and Vite
// passes those calls on to the backend. One address then serves both the page
// and the API, which is what lets a single public link work for UAT testers
// (scripts/run-uat.ps1). In Docker the backend is not on localhost, so
// docker-compose.yml sets BACKEND_URL.
const proxy = {
  "/api": { target: process.env.BACKEND_URL ?? "http://localhost:4000" },
};

// Vite refuses requests addressed to hostnames it does not know. A Cloudflare
// quick tunnel gets a new random *.trycloudflare.com name every time it starts.
const allowedHosts = [".trycloudflare.com"];

export default defineConfig({
  plugins: [react()],
  server: { port: 5173, proxy, allowedHosts },
  preview: { port: 4173, proxy, allowedHosts },
});
