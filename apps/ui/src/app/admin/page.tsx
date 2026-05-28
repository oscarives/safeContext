import { redirect } from 'next/navigation'

// /admin has no content of its own — redirect to the main admin section.
export default function AdminIndexPage() {
  redirect('/admin/tenants')
}
