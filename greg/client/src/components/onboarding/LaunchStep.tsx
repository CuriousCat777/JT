import { useState } from 'react';
import { Rocket, Globe, Users, CheckSquare, Square, PartyPopper, MapPin } from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import { Button } from '@/components/ui/Button';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/Card';
import { Badge } from '@/components/ui/Badge';
import { ProgressBar } from '@/components/ui/ProgressBar';
import { usePracticeStore } from '@/stores/practice-store';

interface ReadinessItem {
  id: string;
  label: string;
  category: 'critical' | 'important' | 'recommended';
  completed: boolean;
}

interface LaunchStepProps {
  onBack: () => void;
}

export default function LaunchStep({ onBack }: LaunchStepProps) {
  const store = usePracticeStore();
  const navigate = useNavigate();

  const [readinessChecklist, setReadinessChecklist] = useState<ReadinessItem[]>([
    { id: 'credentials-verified', label: 'All credentials verified and active', category: 'critical', completed: !!store.stepsCompleted['credentialing'] },
    { id: 'entity-formed', label: 'Business entity formed and registered', category: 'critical', completed: !!store.stepsCompleted['formation'] },
    { id: 'cms-enrolled', label: 'CMS/Medicare enrollment submitted', category: 'critical', completed: store.cmsEnrolled },
    { id: 'hipaa-compliant', label: 'HIPAA compliance checklist complete', category: 'critical', completed: store.hipaaCompliant },
    { id: 'ehr-configured', label: 'EHR system selected and configured', category: 'critical', completed: !!store.ehrSystem },
    { id: 'malpractice-active', label: 'Malpractice insurance active', category: 'critical', completed: !!store.malpracticeInsurance },
    { id: 'billing-setup', label: 'Billing system operational', category: 'important', completed: !!store.billingSystem },
    { id: 'payer-contracts', label: 'At least one payer contract in place', category: 'important', completed: store.payerContracts.length > 0 },
    { id: 'phone-system', label: 'Phone system and scheduling active', category: 'important', completed: false },
    { id: 'website-live', label: 'Practice website published', category: 'recommended', completed: false },
    { id: 'google-listing', label: 'Google Business Profile created', category: 'recommended', completed: false },
    { id: 'directory-listed', label: 'Listed in provider directories', category: 'recommended', completed: false },
  ]);

  const toggleReadiness = (id: string) => {
    setReadinessChecklist((prev) =>
      prev.map((item) => (item.id === id ? { ...item, completed: !item.completed } : item)),
    );
  };

  const criticalItems = readinessChecklist.filter((i) => i.category === 'critical');
  const importantItems = readinessChecklist.filter((i) => i.category === 'important');
  const recommendedItems = readinessChecklist.filter((i) => i.category === 'recommended');

  const completedCount = readinessChecklist.filter((i) => i.completed).length;
  const criticalComplete = criticalItems.every((i) => i.completed);

  const DIRECTORY_LISTINGS = [
    { name: 'Google Business Profile', url: 'business.google.com', status: 'pending' as const },
    { name: 'Healthgrades', url: 'healthgrades.com', status: 'pending' as const },
    { name: 'Vitals.com', url: 'vitals.com', status: 'pending' as const },
    { name: 'WebMD Care', url: 'doctor.webmd.com', status: 'pending' as const },
    { name: 'Zocdoc', url: 'zocdoc.com', status: 'pending' as const },
    { name: 'Psychology Today', url: 'psychologytoday.com', status: 'pending' as const },
  ];

  const handleLaunch = () => {
    store.completeStep('launch');
    navigate('/dashboard');
  };

  return (
    <div className="space-y-8">
      <div>
        <h2 className="text-2xl font-bold text-neutral-900">Launch Readiness</h2>
        <p className="text-neutral-500 mt-1">
          NEXUS coordinates your final launch checklist, directory listings, and community connections.
        </p>
      </div>

      {/* Readiness Score */}
      <Card className="border-primary-200 bg-gradient-to-r from-primary-50 to-white">
        <CardContent className="py-6">
          <div className="flex items-center gap-6">
            <div className="flex-shrink-0">
              <div className="w-20 h-20 rounded-full bg-primary-100 flex items-center justify-center">
                <span className="text-2xl font-bold text-primary-700">
                  {Math.round((completedCount / readinessChecklist.length) * 100)}%
                </span>
              </div>
            </div>
            <div className="flex-1">
              <h3 className="text-lg font-semibold text-neutral-900">Launch Readiness Score</h3>
              <p className="text-sm text-neutral-500 mt-0.5">
                {completedCount} of {readinessChecklist.length} items complete
              </p>
              <ProgressBar
                value={completedCount}
                max={readinessChecklist.length}
                size="md"
                variant={criticalComplete ? 'accent' : 'primary'}
                className="mt-3"
              />
            </div>
            {criticalComplete && (
              <Badge variant="success" className="text-sm px-3 py-1">
                Ready to Launch
              </Badge>
            )}
          </div>
        </CardContent>
      </Card>

      {/* Readiness Checklist */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Rocket className="w-5 h-5 text-primary-600" />
            Go-Live Checklist
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-6">
          {[
            { title: 'Critical (Must Have)', items: criticalItems, variant: 'error' as const },
            { title: 'Important', items: importantItems, variant: 'warning' as const },
            { title: 'Recommended', items: recommendedItems, variant: 'info' as const },
          ].map((section) => (
            <div key={section.title}>
              <div className="flex items-center gap-2 mb-2">
                <h4 className="text-sm font-semibold text-neutral-700">{section.title}</h4>
                <Badge variant={section.variant}>
                  {section.items.filter((i) => i.completed).length}/{section.items.length}
                </Badge>
              </div>
              <div className="space-y-1">
                {section.items.map((item) => (
                  <button
                    key={item.id}
                    type="button"
                    onClick={() => toggleReadiness(item.id)}
                    className="flex items-center gap-3 w-full py-2 px-3 rounded-lg text-left hover:bg-neutral-50 transition-colors"
                  >
                    {item.completed ? (
                      <CheckSquare className="w-5 h-5 text-primary-600 flex-shrink-0" />
                    ) : (
                      <Square className="w-5 h-5 text-neutral-300 flex-shrink-0" />
                    )}
                    <span
                      className={`text-sm ${
                        item.completed ? 'text-neutral-400 line-through' : 'text-neutral-700'
                      }`}
                    >
                      {item.label}
                    </span>
                  </button>
                ))}
              </div>
            </div>
          ))}
        </CardContent>
      </Card>

      {/* Directory Listings */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Globe className="w-5 h-5 text-primary-600" />
            Provider Directory Listings
          </CardTitle>
          <CardDescription>
            Get found by patients -- NEXUS will help you claim and optimize these profiles
          </CardDescription>
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            {DIRECTORY_LISTINGS.map((listing) => (
              <div
                key={listing.name}
                className="flex items-center justify-between p-3 rounded-lg border border-neutral-200 bg-white"
              >
                <div>
                  <p className="text-sm font-medium text-neutral-900">{listing.name}</p>
                  <p className="text-xs text-neutral-400">{listing.url}</p>
                </div>
                <Badge variant="pending">Pending</Badge>
              </div>
            ))}
          </div>
        </CardContent>
      </Card>

      {/* Referral Network */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Users className="w-5 h-5 text-primary-600" />
            Community & Referral Network
          </CardTitle>
          <CardDescription>
            Build relationships with nearby providers in {store.targetCity || 'your area'}
            {store.targetState ? `, ${store.targetState}` : ''}
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-3">
          <div className="p-4 rounded-lg bg-neutral-50 border border-neutral-200">
            <div className="flex items-start gap-3">
              <MapPin className="w-5 h-5 text-accent-600 flex-shrink-0 mt-0.5" />
              <div>
                <p className="text-sm font-medium text-neutral-800">
                  NEXUS will identify in your area:
                </p>
                <ul className="text-sm text-neutral-600 mt-2 space-y-1">
                  <li>- Nearby specialists for referral partnerships</li>
                  <li>- Local hospitals and urgent care facilities</li>
                  <li>- Community health organizations</li>
                  <li>- Medical societies and professional groups</li>
                  <li>- Potential collaboration opportunities</li>
                </ul>
              </div>
            </div>
          </div>

          <div className="p-4 rounded-lg bg-accent-50 border border-accent-200">
            <div className="flex items-start gap-3">
              <PartyPopper className="w-5 h-5 text-accent-600 flex-shrink-0 mt-0.5" />
              <div>
                <p className="text-sm font-medium text-accent-800">Community Outreach Ideas</p>
                <ul className="text-sm text-accent-700 mt-2 space-y-1">
                  <li>- Host an open house / meet-and-greet</li>
                  <li>- Partner with local pharmacies</li>
                  <li>- Offer free blood pressure screenings</li>
                  <li>- Join the local chamber of commerce</li>
                  <li>- Connect with school districts for sports physicals</li>
                </ul>
              </div>
            </div>
          </div>
        </CardContent>
      </Card>

      <div className="flex justify-between pt-4">
        <Button type="button" variant="ghost" onClick={onBack}>
          Back
        </Button>
        <Button type="button" size="lg" variant="secondary" onClick={handleLaunch}>
          <Rocket className="w-4 h-4" />
          Launch My Practice
        </Button>
      </div>
    </div>
  );
}
