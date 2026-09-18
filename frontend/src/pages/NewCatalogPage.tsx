import { useMutation, useQueryClient } from '@tanstack/react-query'
import { type FormEvent, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { createCatalog } from '../api/catalogs'
import { ErrorNotice } from '../components/ErrorNotice'
export function NewCatalogPage() { const [name, setName] = useState(''); const [file, setFile] = useState<File | null>(null); const navigate = useNavigate(); const client = useQueryClient(); const mutation = useMutation({ mutationFn: () => createCatalog(name, file!), onSuccess: (item) => { client.invalidateQueries({ queryKey: ['catalogs'] }); navigate(`/catalogs/${item.id}`) } }); const submit = (event: FormEvent) => { event.preventDefault(); if (file) mutation.mutate() }; return <section className="form-page"><p className="eyebrow">Library</p><h1>Upload reference catalog</h1><form onSubmit={submit}><label>Catalog name<input required value={name} onChange={(event) => setName(event.target.value)} /></label><label>Catalog ZIP<input required type="file" accept=".zip" onChange={(event) => setFile(event.target.files?.[0] ?? null)} /></label><button className="button--primary" disabled={mutation.isPending}>{mutation.isPending ? 'Uploading…' : 'Upload catalog'}</button></form>{mutation.isError && <ErrorNotice message={mutation.error.message} />}</section> }

