interface Props { label: string; index: number; count: number; onPrevious: () => void; onNext: () => void }
export function ImageNavigator({ label, index, count, onPrevious, onNext }: Props) {
  return <div className="navigator"><button type="button" onClick={onPrevious} disabled={index <= 0} aria-label={`Previous ${label}`}>←</button><span>{label} {count ? index + 1 : 0} of {count}</span><button type="button" onClick={onNext} disabled={index >= count - 1} aria-label={`Next ${label}`}>→</button></div>
}

