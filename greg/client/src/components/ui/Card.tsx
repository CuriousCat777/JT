import type { ReactNode, HTMLAttributes } from 'react';
import { cn } from '@/lib/utils';

interface CardProps extends HTMLAttributes<HTMLDivElement> {
  children: ReactNode;
}

function Card({ className, children, ...props }: CardProps) {
  return (
    <div
      className={cn(
        'bg-white rounded-xl border border-neutral-200 card-shadow',
        className,
      )}
      {...props}
    >
      {children}
    </div>
  );
}

function CardHeader({ className, children, ...props }: CardProps) {
  return (
    <div
      className={cn('px-6 py-4 border-b border-neutral-100', className)}
      {...props}
    >
      {children}
    </div>
  );
}

function CardContent({ className, children, ...props }: CardProps) {
  return (
    <div className={cn('px-6 py-4', className)} {...props}>
      {children}
    </div>
  );
}

function CardFooter({ className, children, ...props }: CardProps) {
  return (
    <div
      className={cn('px-6 py-4 border-t border-neutral-100 bg-neutral-50/50 rounded-b-xl', className)}
      {...props}
    >
      {children}
    </div>
  );
}

function CardTitle({ className, children, ...props }: HTMLAttributes<HTMLHeadingElement>) {
  return (
    <h3 className={cn('text-lg font-semibold text-neutral-900', className)} {...props}>
      {children}
    </h3>
  );
}

function CardDescription({ className, children, ...props }: HTMLAttributes<HTMLParagraphElement>) {
  return (
    <p className={cn('text-sm text-neutral-500 mt-1', className)} {...props}>
      {children}
    </p>
  );
}

export { Card, CardHeader, CardContent, CardFooter, CardTitle, CardDescription };
