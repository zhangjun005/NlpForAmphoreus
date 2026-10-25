import { clsx } from 'clsx';
import { twMerge } from 'tailwind-merge';

export function cn(...inputs) { return twMerge(clsx(inputs)); }
export function Card({className='', children}) { return <div className={cn('rounded-2xl border bg-card text-card-foreground shadow-sm',className)}>{children}</div>; }
export function CardHeader({className='', children}) { return <div className={cn('flex flex-col space-y-1.5 p-6',className)}>{children}</div>; }
export function CardTitle({className='', children}) { return <h3 className={cn('font-semibold leading-none tracking-tight',className)}>{children}</h3>; }
export function CardContent({className='', children}) { return <div className={cn('p-6 pt-0',className)}>{children}</div>; }
export function Badge({className='', children}) { return <span className={cn('inline-flex items-center rounded-full border px-2.5 py-0.5 text-xs font-semibold',className)}>{children}</span>; }
export function Button({className='', children, ...props}) { return <button className={cn('inline-flex items-center justify-center rounded-md text-sm font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 disabled:opacity-50',className)} {...props}>{children}</button>; }
