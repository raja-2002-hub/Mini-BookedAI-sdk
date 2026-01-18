import express from 'express';
import path from 'path';

const app = express();
const port = 3000;

// Serve static files from the 'dist/assets' folder
app.use('/assets', express.static(path.resolve(__dirname, 'dist/assets')));

// Start the server
app.listen(port, () => {
  console.log(`Frontend is running at http://localhost:${port}`);
});
