import { Badge } from '@/components/ui/badge'

const variants: Record<string, 'default' | 'secondary' | 'destructive' | 'outline'> = {
  completed: 'default',
  running: 'secondary',
  queued: 'outline',
  failed: 'destructive',
  pass: 'default',
  fail: 'destructive',
}

export function StatusBadge({ status }: { status: string }) {
  return (
    <Badge variant={variants[status] ?? 'outline'} className="font-mono uppercase">
      {status}
    </Badge>
  )
}
