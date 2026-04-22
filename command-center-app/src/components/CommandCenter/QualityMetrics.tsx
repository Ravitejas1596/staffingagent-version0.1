import type { QualityMetrics as QualityMetricsType } from './types';

interface QualityMetricsProps {
  data: QualityMetricsType | null;
  isLoading: boolean;
}

const CIRCUMFERENCE = 2 * Math.PI * 35; // r=35

interface GaugeProps {
  value: number;
  color: string;
  label: string;
}

function CircularGauge({ value, color, label }: GaugeProps) {
  const offset = CIRCUMFERENCE - (value / 100) * CIRCUMFERENCE;

  return (
    <div className="cc-quality-card">
      <div className="cc-quality-gauge">
        <svg width="80" height="80" viewBox="0 0 80 80">
          <circle className="cc-quality-gauge-bg" cx="40" cy="40" r="35" />
          <circle
            className="cc-quality-gauge-fill"
            cx="40" cy="40" r="35"
            stroke={color}
            strokeDasharray={CIRCUMFERENCE}
            strokeDashoffset={offset}
          />
        </svg>
        <div className="cc-quality-gauge-value" style={{ color }}>{value}%</div>
      </div>
      <div className="cc-quality-label">{label}</div>
    </div>
  );
}

export default function QualityMetrics({ data, isLoading }: QualityMetricsProps) {
  if (isLoading || !data) {
    return (
      <section className="cc-quality-grid">
        {Array.from({ length: 4 }).map((_, i) => (
          <div key={i} className="cc-quality-card">
            <div className="cc-skeleton" style={{ width: 80, height: 80, borderRadius: '50%', margin: '0 auto 12px' }} />
            <div className="cc-skeleton" style={{ width: '70%', height: 12, margin: '0 auto' }} />
          </div>
        ))}
      </section>
    );
  }

  return (
    <section className="cc-quality-grid">
      <CircularGauge value={data.firstPassAccuracy} color="var(--cc-green)" label="First-Pass Accuracy" />
      <CircularGauge value={data.autoResolutionRate} color="var(--cc-cyan)" label="Auto-Resolution Rate" />
      <CircularGauge value={data.humanOverrideRate} color="var(--cc-purple)" label="Human Override Rate" />
      <CircularGauge value={data.falsePositiveRate} color="var(--cc-amber)" label="False Positive Rate" />
    </section>
  );
}
