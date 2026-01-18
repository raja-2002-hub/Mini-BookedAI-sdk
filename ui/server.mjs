// server.mjs
import express from "express";
import path from "path";
import { fileURLToPath } from "url";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

const app = express();
const PORT = process.env.PORT ? Number(process.env.PORT) : 4444;

// serve the whole dist directory (index.html + assets)
app.use(express.static(path.resolve(__dirname, "dist")));

app.listen(PORT, () => {
  console.log(`Static assets server running at http://localhost:${PORT}`);
});
