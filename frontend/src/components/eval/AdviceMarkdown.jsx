/** 优化建议文本的统一渲染：清洗模型噪声 + markdown（GFM）。AdvicePanel / InsightsPanel 共用。 */
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'

// markdown 渲染样式（与 EvalPrompts 保持一致）
const MD = {
  h1: (p) => <h1 className="text-base font-bold mt-3 mb-2" {...p} />,
  h2: (p) => <h2 className="text-sm font-bold mt-3 mb-1.5" {...p} />,
  h3: (p) => <h3 className="text-sm font-semibold mt-2 mb-1" {...p} />,
  p:  (p) => <p className="my-1.5 leading-relaxed text-sm text-gray-700" {...p} />,
  ul: (p) => <ul className="list-disc pl-5 my-1.5 space-y-0.5 text-sm text-gray-700" {...p} />,
  ol: (p) => <ol className="list-decimal pl-5 my-1.5 space-y-0.5 text-sm text-gray-700" {...p} />,
  li: (p) => <li className="leading-relaxed" {...p} />,
  code: (p) => <code className="rounded bg-gray-200 px-1 py-0.5 text-[0.85em] font-mono" {...p} />,
  pre: (p) => <pre className="rounded bg-gray-100 p-2 my-2 overflow-x-auto text-xs" {...p} />,
  blockquote: (p) => <blockquote className="border-l-2 border-gray-300 pl-3 italic text-muted-foreground my-2 text-sm" {...p} />,
  table: (p) => <table className="border-collapse my-2 text-xs" {...p} />,
  th: (p) => <th className="border border-gray-300 px-2 py-1 bg-gray-100 text-left" {...p} />,
  td: (p) => <td className="border border-gray-300 px-2 py-1" {...p} />,
  a:  (p) => <a className="text-blue-600 underline" {...p} />,
}

/**
 * 清洗模型输出的噪声，保证 markdown 干净可渲染：
 * 模型偶尔吐图片/HTML 徽章（react-markdown 不渲染 → 坏图/原文）、连续感叹号星号等噪声。
 * 提示词已约束，这里是前端兜底。
 */
export function sanitizeAdviceText(text) {
  if (!text) return ''
  return text
    .replace(/!\[[^\]]*\]\([^)]*\)/g, '')        // 去图片 ![alt](url)（含 shields.io 徽章）
    .replace(/<\/?[a-zA-Z][^>]*>/g, '')          // 去裸 HTML 标签 <span> </div> 等
    .replace(/[!！]{2,}/g, '')                    // 连续感叹号噪声
    .replace(/\*{3,}/g, '**')                     // 3+ 连星折成加粗
    .replace(/\n{3,}/g, '\n\n')                   // 多余空行收敛
    .trim()
}

/** 渲染一段优化建议文本（清洗 + GFM markdown）。 */
export default function AdviceMarkdown({ text }) {
  return (
    <ReactMarkdown remarkPlugins={[remarkGfm]} components={MD}>
      {sanitizeAdviceText(text) || '_（无内容）_'}
    </ReactMarkdown>
  )
}
