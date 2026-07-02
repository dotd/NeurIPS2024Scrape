const express = require('express');
const path = require('path');
const fs = require('fs');

const PORT = process.env.PORT || 3000;
const HOST = process.env.HOST || '127.0.0.1';

const app = express();
const papersPath = path.join(__dirname, 'data', 'papers.json');
const papers = JSON.parse(fs.readFileSync(papersPath, 'utf-8'));

app.use(express.static(path.join(__dirname, 'public')));

app.get('/api/papers', (_req, res) => {
  res.json(papers);
});

app.get('/api/meta', (_req, res) => {
  res.json({
    count: papers.papers.length,
    generated_at: papers.generated_at,
    source: papers.source,
    patterns: papers.patterns,
  });
});

app.listen(PORT, HOST, () => {
  console.log(`ICLR 2026 world-model site running at http://${HOST}:${PORT}`);
  console.log(`Serving ${papers.papers.length} papers from ${papersPath}`);
});
