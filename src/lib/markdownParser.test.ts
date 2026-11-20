import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { parseMarkdownBlocks } from './markdownParser.ts';

test('parses every real study Markdown report cleanly without hanging', () => {
  const studiesDir = path.resolve(process.cwd(), 'docs/studies');
  const files = fs.readdirSync(studiesDir).filter((f) => f.endsWith('.md')).sort();
  assert.equal(files.length, 13);

  for (const file of files) {
    const content = fs.readFileSync(path.join(studiesDir, file), 'utf-8');
    const blocks = parseMarkdownBlocks(content);
    assert.ok(blocks.length > 5, `${file} should produce structured markdown blocks`);
    assert.equal(blocks[0].type, 'heading', `${file} should begin with a heading`);
  }
});

test('handles h4 headings, blockquotes, and standalone pipe lines safely', () => {
  const sample = `#### Sub-heading\n> A quoted note\n| stray pipe without separator\n\nParagraph text.`;
  const blocks = parseMarkdownBlocks(sample);
  assert.equal(blocks[0].type, 'heading');
  assert.equal(blocks[1].type, 'blockquote');
  assert.equal(blocks[2].type, 'paragraph');
  assert.equal(blocks[3].type, 'paragraph');
});
