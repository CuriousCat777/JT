import { DollarSign, Calculator, FileSpreadsheet, Handshake } from 'lucide-react';
import { Button } from '@/components/ui/Button';
import { Input } from '@/components/ui/Input';
import { Select } from '@/components/ui/Select';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/Card';
import { Badge } from '@/components/ui/Badge';
import { usePracticeStore } from '@/stores/practice-store';

const BILLING_SYSTEMS = [
  { value: 'athena-rcm', label: 'athenahealth RCM' },
  { value: 'kareo-billing', label: 'Kareo / Tebra Billing' },
  { value: 'advancedmd', label: 'AdvancedMD' },
  { value: 'collaboratemd', label: 'CollaborateMD' },
  { value: 'ehr-integrated', label: 'EHR-Integrated Billing' },
  { value: 'outsourced', label: 'Outsourced Billing Service' },
  { value: 'undecided', label: 'Not decided yet' },
];

interface BudgetItem {
  category: string;
  items: { name: string; low: string; high: string; note?: string }[];
}

const STARTUP_BUDGET: BudgetItem[] = [
  {
    category: 'Facility',
    items: [
      { name: 'Lease deposit & first month', low: '$3,000', high: '$15,000', note: 'Varies by market' },
      { name: 'Tenant improvements', low: '$10,000', high: '$50,000' },
      { name: 'Signage', low: '$500', high: '$5,000' },
    ],
  },
  {
    category: 'Equipment & Technology',
    items: [
      { name: 'EHR system (annual)', low: '$3,600', high: '$24,000' },
      { name: 'Medical equipment', low: '$5,000', high: '$30,000' },
      { name: 'Computers & peripherals', low: '$2,000', high: '$8,000' },
      { name: 'Phone/internet setup', low: '$500', high: '$3,000' },
    ],
  },
  {
    category: 'Legal & Administrative',
    items: [
      { name: 'Entity formation', low: '$500', high: '$3,000' },
      { name: 'Malpractice insurance (annual)', low: '$5,000', high: '$25,000' },
      { name: 'Business insurance', low: '$1,000', high: '$5,000' },
      { name: 'Credentialing services', low: '$0', high: '$5,000' },
    ],
  },
  {
    category: 'Working Capital',
    items: [
      { name: '3-6 months operating expenses', low: '$30,000', high: '$150,000', note: 'Critical buffer' },
      { name: 'Marketing & patient acquisition', low: '$2,000', high: '$15,000' },
    ],
  },
];

const PAYER_OPTIONS = [
  'Medicare',
  'Medicaid',
  'Blue Cross Blue Shield',
  'UnitedHealthcare',
  'Aetna',
  'Cigna',
  'Humana',
  'Tricare',
];

interface FinancialStepProps {
  onComplete: () => void;
  onBack: () => void;
}

export default function FinancialStep({ onComplete, onBack }: FinancialStepProps) {
  const store = usePracticeStore();

  const togglePayer = (payer: string) => {
    const current = store.payerContracts;
    if (current.includes(payer)) {
      store.setField(
        'payerContracts',
        current.filter((p) => p !== payer),
      );
    } else {
      store.setField('payerContracts', [...current, payer]);
    }
  };

  const handleContinue = () => {
    store.completeStep('financial');
    onComplete();
  };

  return (
    <div className="space-y-8">
      <div>
        <h2 className="text-2xl font-bold text-neutral-900">Financial Setup</h2>
        <p className="text-neutral-500 mt-1">
          LEDGER configures your billing, budgets, fee schedules, and payer contracts.
        </p>
      </div>

      {/* Billing system */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Calculator className="w-5 h-5 text-primary-600" />
            Billing & Revenue Cycle
          </CardTitle>
          <CardDescription>
            Choose how you will handle medical billing and collections
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <Select
            label="Billing System"
            placeholder="Select billing solution"
            options={BILLING_SYSTEMS}
            value={store.billingSystem}
            onChange={(e) => store.setField('billingSystem', e.target.value)}
          />
          <div className="flex items-center gap-3">
            <label className="flex items-center gap-2 text-sm text-neutral-700 cursor-pointer">
              <input
                type="checkbox"
                checked={store.feeScheduleSet}
                onChange={(e) => store.setField('feeScheduleSet', e.target.checked)}
                className="rounded border-neutral-300 text-primary-600 focus:ring-primary-500"
              />
              I have established a fee schedule
            </label>
          </div>
        </CardContent>
      </Card>

      {/* Startup Budget */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <DollarSign className="w-5 h-5 text-primary-600" />
            Startup Budget Estimate
          </CardTitle>
          <CardDescription>
            Estimated costs for a {store.practiceType || 'solo'} {store.specialty || 'primary care'} practice
          </CardDescription>
        </CardHeader>
        <CardContent>
          <div className="space-y-6">
            {STARTUP_BUDGET.map((section) => (
              <div key={section.category}>
                <h4 className="text-sm font-semibold text-neutral-700 mb-2">
                  {section.category}
                </h4>
                <div className="space-y-2">
                  {section.items.map((item) => (
                    <div
                      key={item.name}
                      className="flex items-center justify-between text-sm py-1.5 px-3 rounded bg-neutral-50"
                    >
                      <div>
                        <span className="text-neutral-700">{item.name}</span>
                        {item.note && (
                          <span className="text-xs text-neutral-400 ml-2">({item.note})</span>
                        )}
                      </div>
                      <span className="font-mono text-neutral-600">
                        {item.low} - {item.high}
                      </span>
                    </div>
                  ))}
                </div>
              </div>
            ))}
            <div className="flex items-center justify-between pt-3 border-t border-neutral-200">
              <span className="font-semibold text-neutral-900">Estimated Total Range</span>
              <span className="font-mono font-semibold text-primary-700">
                $62,100 - $338,000
              </span>
            </div>
          </div>

          <div className="mt-4">
            <Input
              label="Your Target Budget"
              placeholder="e.g., $150,000"
              value={store.startupBudget}
              onChange={(e) => store.setField('startupBudget', e.target.value)}
              helperText="LEDGER will tailor recommendations to your budget"
            />
          </div>
        </CardContent>
      </Card>

      {/* Fee Schedule */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <FileSpreadsheet className="w-5 h-5 text-primary-600" />
            Fee Schedule
          </CardTitle>
          <CardDescription>
            LEDGER will generate a fee schedule based on Medicare rates and local market data
          </CardDescription>
        </CardHeader>
        <CardContent>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-neutral-200">
                  <th className="text-left py-2 font-medium text-neutral-600">CPT Code</th>
                  <th className="text-left py-2 font-medium text-neutral-600">Description</th>
                  <th className="text-right py-2 font-medium text-neutral-600">Medicare</th>
                  <th className="text-right py-2 font-medium text-neutral-600">Suggested</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-neutral-100">
                {[
                  { code: '99213', desc: 'Office visit, established, low', medicare: '$92', suggested: '$135' },
                  { code: '99214', desc: 'Office visit, established, moderate', medicare: '$131', suggested: '$190' },
                  { code: '99215', desc: 'Office visit, established, high', medicare: '$176', suggested: '$260' },
                  { code: '99203', desc: 'Office visit, new, low', medicare: '$110', suggested: '$165' },
                  { code: '99204', desc: 'Office visit, new, moderate', medicare: '$167', suggested: '$250' },
                  { code: '99205', desc: 'Office visit, new, high', medicare: '$211', suggested: '$315' },
                  { code: '99395', desc: 'Preventive visit, 18-39', medicare: '$153', suggested: '$225' },
                  { code: '99396', desc: 'Preventive visit, 40-64', medicare: '$166', suggested: '$245' },
                ].map((row) => (
                  <tr key={row.code}>
                    <td className="py-2 font-mono text-neutral-700">{row.code}</td>
                    <td className="py-2 text-neutral-600">{row.desc}</td>
                    <td className="py-2 text-right font-mono text-neutral-500">{row.medicare}</td>
                    <td className="py-2 text-right font-mono font-medium text-primary-700">
                      {row.suggested}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="text-xs text-neutral-400 mt-3">
            Suggested rates are approximately 1.5x Medicare rates. Adjust based on local market conditions.
          </p>
        </CardContent>
      </Card>

      {/* Payer Contracts */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Handshake className="w-5 h-5 text-primary-600" />
            Payer Contracts
          </CardTitle>
          <CardDescription>
            Select insurance payers you plan to contract with
          </CardDescription>
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            {PAYER_OPTIONS.map((payer) => {
              const isSelected = store.payerContracts.includes(payer);
              return (
                <button
                  key={payer}
                  type="button"
                  onClick={() => togglePayer(payer)}
                  className={`p-3 rounded-lg border text-sm font-medium text-center transition-colors ${
                    isSelected
                      ? 'border-primary-300 bg-primary-50 text-primary-700'
                      : 'border-neutral-200 bg-white text-neutral-600 hover:border-neutral-300'
                  }`}
                >
                  {payer}
                  {isSelected && (
                    <Badge variant="success" className="mt-1.5 mx-auto">
                      Selected
                    </Badge>
                  )}
                </button>
              );
            })}
          </div>
          <p className="text-xs text-neutral-400 mt-3">
            Credentialing with each payer typically takes 60-120 days. Start early.
          </p>
        </CardContent>
      </Card>

      <div className="flex justify-between pt-4">
        <Button type="button" variant="ghost" onClick={onBack}>
          Back
        </Button>
        <Button type="button" onClick={handleContinue}>
          Continue to Launch
        </Button>
      </div>
    </div>
  );
}
