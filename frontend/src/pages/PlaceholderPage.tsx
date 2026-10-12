import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'

export function PlaceholderPage({ title }: { title: string }) {
  return (
    <section className="space-y-4">
      <p className="text-xs uppercase tracking-widest text-muted-foreground">Not migrated yet</p>
      <h1 className="text-3xl font-medium">{title}</h1>
      <Alert>
        <AlertTitle>Jinja remains the source of truth</AlertTitle>
        <AlertDescription>
          This view is not part of the React shell. Use the Flask pages at the site root until
          keyboard and mobile parity is documented.
        </AlertDescription>
      </Alert>
    </section>
  )
}
