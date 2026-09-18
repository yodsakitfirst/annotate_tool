import { useQuery } from '@tanstack/react-query'
import { useState } from 'react'
import { listCatalogClasses } from '../api/catalogs'

interface Props { catalogId: string; selectedClassId: number; onSelect: (id: number) => void; disabled: boolean }
export function ReferenceClassBrowser({ catalogId, selectedClassId, onSelect, disabled }: Props) {
  const [query, setQuery] = useState('')
  const [offset, setOffset] = useState(0)
  const classes = useQuery({ queryKey: ['catalog-classes', catalogId, query, offset], queryFn: () => listCatalogClasses(catalogId, query, offset) })
  return <section className="class-browser"><label>Find a class<input type="search" value={query} onChange={(event) => { setQuery(event.target.value); setOffset(0) }} /></label>
    <div className="class-grid">{classes.data?.items.map((item) => <button type="button" key={item.class_id} className={item.class_id === selectedClassId ? 'is-selected' : ''} onClick={() => onSelect(item.class_id)} disabled={disabled} aria-label={`${item.name} class ${item.class_id}`}><img src={item.thumbnail_url} alt="" loading="lazy" /><span>{item.class_id} · {item.name}</span></button>)}</div>
    {classes.isLoading && <p>Loading classes…</p>}{classes.isError && <p role="alert">Could not load reference classes.</p>}
    <div className="navigator"><button type="button" disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - 50))}>Previous classes</button><button type="button" disabled={(classes.data?.items.length ?? 0) < 50} onClick={() => setOffset(offset + 50)}>Next classes</button></div>
  </section>
}
