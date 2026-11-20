import React from 'react';
import { parseMarkdownBlocks } from '../lib/markdownParser';

interface MarkdownViewerProps {
  content: string;
}

function renderInline(text: string): React.ReactNode[] {
  const tokens: React.ReactNode[] = [];
  const regex = /(`[^`]+`|\*\*[^*]+\*\*|\*[^*]+\*)/g;
  let lastIndex = 0;
  let match: RegExpExecArray | null;
  let key = 0;

  while ((match = regex.exec(text)) !== null) {
    if (match.index > lastIndex) {
      tokens.push(text.slice(lastIndex, match.index));
    }
    const raw = match[0];
    if (raw.startsWith('`') && raw.endsWith('`')) {
      tokens.push(
        <code
          key={key++}
          className="font-mono text-[12.5px] bg-slate-100 text-slate-800 px-1 py-0.5 rounded"
        >
          {raw.slice(1, -1)}
        </code>,
      );
    } else if (raw.startsWith('**') && raw.endsWith('**')) {
      tokens.push(
        <strong key={key++} className="font-semibold text-slate-900">
          {raw.slice(2, -2)}
        </strong>,
      );
    } else if (raw.startsWith('*') && raw.endsWith('*')) {
      tokens.push(
        <em key={key++} className="italic">
          {raw.slice(1, -1)}
        </em>,
      );
    }
    lastIndex = match.index + raw.length;
  }

  if (lastIndex < text.length) {
    tokens.push(text.slice(lastIndex));
  }
  return tokens;
}

export const MarkdownViewer: React.FC<MarkdownViewerProps> = ({ content }) => {
  const blocks = React.useMemo(() => parseMarkdownBlocks(content), [content]);

  if (blocks.length === 0) {
    return (
      <p className="text-sm text-slate-500">No Markdown study report found for this entry.</p>
    );
  }

  return (
    <div>
      {blocks.map((block, idx) => {
        if (block.type === 'code') {
          return (
            <pre
              key={idx}
              className="overflow-x-auto bg-slate-900 text-slate-100 p-4 rounded-lg text-xs font-mono leading-relaxed my-4"
            >
              <code>{block.content}</code>
            </pre>
          );
        }
        if (block.type === 'heading') {
          if (block.level === 1) {
            return (
              <h1 key={idx} className="text-2xl font-bold text-slate-900 tracking-tight mb-3 mt-1">
                {renderInline(block.text)}
              </h1>
            );
          }
          if (block.level === 2) {
            return (
              <h2
                key={idx}
                className="text-base font-semibold text-slate-900 tracking-tight mt-7 mb-2.5 pb-1.5 border-b border-slate-200"
              >
                {renderInline(block.text)}
              </h2>
            );
          }
          if (block.level === 3) {
            return (
              <h3 key={idx} className="text-sm font-semibold text-slate-800 mt-5 mb-2">
                {renderInline(block.text)}
              </h3>
            );
          }
          return (
            <h4 key={idx} className="text-xs font-semibold text-slate-700 mt-4 mb-1.5">
              {renderInline(block.text)}
            </h4>
          );
        }
        if (block.type === 'hr') {
          return <hr key={idx} className="my-5 border-slate-200" />;
        }
        if (block.type === 'blockquote') {
          return (
            <blockquote
              key={idx}
              className="my-4 px-4 py-3 bg-slate-50 border border-slate-200 rounded-md text-xs text-slate-700 leading-relaxed"
            >
              {renderInline(block.text)}
            </blockquote>
          );
        }
        if (block.type === 'table') {
          return (
            <div key={idx} className="overflow-x-auto my-4 border border-slate-200 rounded-lg">
              <table className="w-full text-left border-collapse text-xs">
                <thead>
                  <tr className="bg-slate-50 border-b border-slate-200 text-slate-600">
                    {block.headers.map((h, hIdx) => (
                      <th key={hIdx} className="py-2.5 px-3 font-semibold whitespace-nowrap">
                        {renderInline(h)}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100">
                  {block.rows.map((row, rIdx) => (
                    <tr key={rIdx} className="hover:bg-slate-50/80">
                      {row.map((cell, cIdx) => {
                        const isNumeric = /^[-−+]?\d/.test(cell) || cell.endsWith('%');
                        return (
                          <td
                            key={cIdx}
                            className={`py-2 px-3 text-slate-700 align-top ${
                              isNumeric ? 'font-mono tabular-nums whitespace-nowrap' : ''
                            }`}
                          >
                            {renderInline(cell)}
                          </td>
                        );
                      })}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          );
        }
        if (block.type === 'ul') {
          return (
            <ul
              key={idx}
              className="list-disc pl-5 space-y-1.5 my-3 text-sm text-slate-700 leading-relaxed"
            >
              {block.items.map((item, iIdx) => (
                <li key={iIdx}>{renderInline(item)}</li>
              ))}
            </ul>
          );
        }
        if (block.type === 'ol') {
          return (
            <ol
              key={idx}
              className="list-decimal pl-5 space-y-1.5 my-3 text-sm text-slate-700 leading-relaxed"
            >
              {block.items.map((item, iIdx) => (
                <li key={iIdx}>{renderInline(item)}</li>
              ))}
            </ol>
          );
        }
        return (
          <p key={idx} className="text-sm text-slate-700 leading-relaxed my-3 max-w-[75ch]">
            {renderInline(block.text)}
          </p>
        );
      })}
    </div>
  );
};
