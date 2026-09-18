import { useQuery } from '@tanstack/react-query'
import { useParams } from 'react-router-dom'
import { getCatalog, listCatalogClasses } from '../api/catalogs'
export function CatalogDetailPage() { const { catalogId = '' } = useParams(); const catalog = useQuery({ queryKey: ['catalog', catalogId], queryFn: () => getCatalog(catalogId) }); const classes = useQuery({ queryKey: ['catalog-classes', catalogId, ''], queryFn: () => listCatalogClasses(catalogId) }); if (catalog.isLoading) return <p>Loading catalog…</p>; return <section><p className="eyebrow">Reference catalog</p><h1>{catalog.data?.name}</h1><div className="detail-grid">{classes.data?.items.map((item) => <article key={item.class_id}><img src={item.thumbnail_url} alt="" loading="lazy" /><b>{item.class_id} · {item.name}</b></article>)}</div></section> }

