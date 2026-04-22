import './Skeleton.css';

interface SkeletonProps {
  variant?: 'text' | 'rect' | 'card';
  width?: string | number;
  height?: string | number;
  count?: number;
  className?: string;
}

export default function Skeleton({
  variant = 'rect',
  width = '100%',
  height = 16,
  count = 1,
  className = '',
}: SkeletonProps) {
  const items = Array.from({ length: count });
  return (
    <>
      {items.map((_, i) => (
        <div
          key={i}
          className={`sa-skeleton sa-skeleton-${variant} ${className}`.trim()}
          style={{ width, height, marginBottom: count > 1 ? 8 : 0 }}
          aria-hidden="true"
        />
      ))}
    </>
  );
}

export function DashboardSkeleton() {
  return (
    <div className="entity-panels" aria-busy="true" aria-label="Loading dashboard">
      {[1, 2, 3, 4, 5].map((i) => (
        <div
          key={i}
          style={{
            padding: 16,
            border: '1.5px solid #e2e8f0',
            borderRadius: 14,
            background: '#ffffff',
          }}
        >
          <Skeleton height={18} width="55%" />
          <div style={{ height: 14 }} />
          <Skeleton count={4} height={28} />
          <div style={{ height: 10 }} />
          <Skeleton height={8} variant="text" />
        </div>
      ))}
    </div>
  );
}

export function TableSkeleton({ rows = 8, columns = 10 }: { rows?: number; columns?: number }) {
  const widthPct = `${100 / columns}%`;
  return (
    <div aria-busy="true" aria-label="Loading records">
      {Array.from({ length: rows }).map((_, r) => (
        <div
          key={r}
          style={{
            display: 'flex',
            gap: 8,
            padding: '10px 0',
            borderBottom: '1px solid #f1f5f9',
          }}
        >
          {Array.from({ length: columns }).map((_, c) => (
            <Skeleton key={c} height={14} width={widthPct} />
          ))}
        </div>
      ))}
    </div>
  );
}

export function RiskCategoriesSkeleton() {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 8, marginBottom: 16 }} aria-busy="true">
      <div style={{ padding: 16, border: '1.5px solid #e2e8f0', borderRadius: 14 }}>
        <Skeleton height={20} width="40%" />
      </div>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 8 }}>
        {[1, 2, 3, 4, 5, 6].map((i) => (
          <div key={i} style={{ padding: 16, border: '1.5px solid #e2e8f0', borderRadius: 14 }}>
            <Skeleton height={16} width="70%" />
            <div style={{ height: 8 }} />
            <Skeleton height={24} width="30%" />
          </div>
        ))}
      </div>
    </div>
  );
}
