import { articleUrl, sourceAnchor, type ResearchSource } from './sources'

// Transform only Markdown text/link nodes. Code blocks and inline code retain their original text.
type Node = { type: string; value?: string; url?: string; title?: string; children?: Node[] }
export function citationPlugin(sources: ResearchSource[], scope: string, pending: boolean) {
  const byId = new Map(sources.map((source, i) => [source.id, { source, index: i + 1 }]))
  const token = /\[?(src_[0-9a-f]{24})\]?/g
  function link(id: string): Node {
    const entry = byId.get(id)
    return entry ? { type: 'link', url: articleUrl(entry.source) || `#${sourceAnchor(scope, id)}`, title: entry.source.title,
      children: [{ type: 'text', value: `[${entry.index}]` }] } :
      { type: 'link', url: '#unresolved-citation', children: [{ type: 'text', value: pending ? '来源加载中' : '来源未找到' }] }
  }
  function walk(node: Node) {
    if (!node.children) return
    node.children = node.children.flatMap(child => {
      if (child.type === 'link') {
        const id = child.children?.map(n => n.value || '').join('').match(/src_[0-9a-f]{24}/)?.[0] || child.url?.match(/^src_[0-9a-f]{24}$/)?.[0]
        if (id) return [link(id)]
        // Historical answers may link directly to an authenticated provider endpoint.
        const source = sources.find(s => s.url === child.url)
        if (source && !articleUrl(source)) return [{ ...child, url: `#${sourceAnchor(scope, source.id)}` }]
        return [child]
      }
      if (child.type !== 'text' || !child.value) { walk(child); return [child] }
      const nodes: Node[] = [], text = child.value
      let cursor = 0
      for (const match of text.matchAll(token)) {
        if (match.index! > cursor) nodes.push({ type: 'text', value: text.slice(cursor, match.index) })
        nodes.push(link(match[1])); cursor = match.index! + match[0].length
      }
      const tail = text.slice(cursor)
      const partial = pending ? tail.match(/\[?src_[0-9a-f]{0,23}$/) : null
      if (partial) {
        if (partial.index! > 0) nodes.push({ type: 'text', value: tail.slice(0, partial.index) })
        nodes.push({ type: 'link', url: '#unresolved-citation', children: [{ type: 'text', value: '来源加载中' }] })
      } else if (!nodes.length) return [child]
      else if (tail) nodes.push({ type: 'text', value: tail })
      return nodes
    })
  }
  return () => (tree: Node) => walk(tree)
}
