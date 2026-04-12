import { Link } from 'react-router-dom';
import {
  Stethoscope,
  Shield,
  Building2,
  ShieldCheck,
  Monitor,
  DollarSign,
  Users,
  ArrowRight,
  Bell,
  Clock,
  TrendingUp,
  CheckCircle2,
  AlertCircle,
} from 'lucide-react';
import { Button } from '@/components/ui/Button';
import { Card, CardContent, CardHeader, CardTitle, CardDescription, CardFooter } from '@/components/ui/Card';
import { Badge } from '@/components/ui/Badge';
import { ProgressBar } from '@/components/ui/ProgressBar';
import { usePracticeStore } from '@/stores/practice-store';

interface DashboardProps {
  section?: string;
}

interface DashboardCard {
  id: string;
  title: string;
  agent: string;
  icon: React.ReactNode;
  route: string;
  progress: number;
  status: 'complete' | 'in-progress' | 'not-started';
  tasks: { label: string; done: boolean }[];
}

export default function Dashboard({ section }: DashboardProps) {
  const store = usePracticeStore();

  const getProgress = (stepId: string): number => {
    if (store.stepsCompleted[stepId]) return 100;
    // Calculate partial progress based on filled fields
    switch (stepId) {
      case 'credentialing':
        return [store.npiNumber, store.stateLicense, store.deaNumber, store.boardCertification]
          .filter(Boolean).length * 25;
      case 'formation':
        return [store.practiceName, store.entityType, store.ein].filter(Boolean).length * 33;
      case 'compliance':
        return [store.cmsEnrolled, store.hipaaCompliant, store.oigClear].filter(Boolean).length * 33;
      case 'clinical':
        return [store.ehrSystem, store.ePrescribing, store.labConnectivity, store.fhirEnabled]
          .filter(Boolean).length * 25;
      case 'financial':
        return [store.billingSystem, store.startupBudget, store.feeScheduleSet, store.payerContracts.length > 0]
          .filter(Boolean).length * 25;
      case 'launch':
        return store.stepsCompleted['launch'] ? 100 : 0;
      default:
        return 0;
    }
  };

  const getStatus = (stepId: string): 'complete' | 'in-progress' | 'not-started' => {
    if (store.stepsCompleted[stepId]) return 'complete';
    if (getProgress(stepId) > 0) return 'in-progress';
    return 'not-started';
  };

  const cards: DashboardCard[] = [
    {
      id: 'credentials',
      title: 'Credentialing',
      agent: 'CREDENCE',
      icon: <Shield className="w-5 h-5 text-blue-600" />,
      route: '/dashboard/credentials',
      progress: getProgress('credentialing'),
      status: getStatus('credentialing'),
      tasks: [
        { label: 'NPI verified', done: !!store.npiNumber },
        { label: 'State license verified', done: !!store.stateLicense },
        { label: 'DEA registration', done: !!store.deaNumber },
        { label: 'Board certification', done: !!store.boardCertification },
      ],
    },
    {
      id: 'formation',
      title: 'Business Formation',
      agent: 'FORMA',
      icon: <Building2 className="w-5 h-5 text-emerald-600" />,
      route: '/dashboard/formation',
      progress: getProgress('formation'),
      status: getStatus('formation'),
      tasks: [
        { label: 'Practice name registered', done: !!store.practiceName },
        { label: 'Entity type selected', done: !!store.entityType },
        { label: 'EIN obtained', done: !!store.ein },
        { label: 'Business address set', done: !!store.businessAddress },
      ],
    },
    {
      id: 'compliance',
      title: 'Compliance',
      agent: 'COMPLY',
      icon: <ShieldCheck className="w-5 h-5 text-violet-600" />,
      route: '/dashboard/compliance',
      progress: getProgress('compliance'),
      status: getStatus('compliance'),
      tasks: [
        { label: 'CMS enrollment', done: store.cmsEnrolled },
        { label: 'HIPAA program', done: store.hipaaCompliant },
        { label: 'OIG check clear', done: store.oigClear },
        { label: 'CLIA waiver (if needed)', done: !store.cliaRequired || !!store.cliaNumber },
      ],
    },
    {
      id: 'clinical',
      title: 'Clinical Setup',
      agent: 'VITALS',
      icon: <Monitor className="w-5 h-5 text-rose-600" />,
      route: '/dashboard/clinical',
      progress: getProgress('clinical'),
      status: getStatus('clinical'),
      tasks: [
        { label: 'EHR configured', done: !!store.ehrSystem },
        { label: 'e-Prescribing active', done: store.ePrescribing },
        { label: 'Lab connectivity', done: store.labConnectivity },
        { label: 'FHIR bridge enabled', done: store.fhirEnabled },
      ],
    },
    {
      id: 'financial',
      title: 'Financial',
      agent: 'LEDGER',
      icon: <DollarSign className="w-5 h-5 text-amber-600" />,
      route: '/dashboard/financial',
      progress: getProgress('financial'),
      status: getStatus('financial'),
      tasks: [
        { label: 'Billing system selected', done: !!store.billingSystem },
        { label: 'Budget allocated', done: !!store.startupBudget },
        { label: 'Fee schedule set', done: store.feeScheduleSet },
        { label: 'Payer contracts', done: store.payerContracts.length > 0 },
      ],
    },
    {
      id: 'network',
      title: 'Network & Launch',
      agent: 'NEXUS',
      icon: <Users className="w-5 h-5 text-teal-600" />,
      route: '/dashboard/network',
      progress: getProgress('launch'),
      status: getStatus('launch'),
      tasks: [
        { label: 'Directory listings', done: store.directoryListings.length > 0 },
        { label: 'Referral partners', done: store.referralPartners.length > 0 },
        { label: 'Community outreach', done: false },
        { label: 'Go-live readiness', done: store.stepsCompleted['launch'] ?? false },
      ],
    },
  ];

  const overallProgress = Math.round(
    cards.reduce((sum, c) => sum + c.progress, 0) / cards.length,
  );

  const statusBadge = (status: DashboardCard['status']) => {
    switch (status) {
      case 'complete':
        return <Badge variant="success">Complete</Badge>;
      case 'in-progress':
        return <Badge variant="warning">In Progress</Badge>;
      default:
        return <Badge variant="pending">Not Started</Badge>;
    }
  };

  const recentActivity = [
    { time: 'Just now', message: 'Dashboard loaded', type: 'info' as const },
    { time: '2 min ago', message: 'Assessment completed', type: 'success' as const },
    { time: '5 min ago', message: 'Practice store initialized', type: 'info' as const },
  ];

  // If a specific section is selected, we could show a detail view.
  // For now, the dashboard always shows the overview with section highlight.
  const activeSection = section;

  return (
    <div className="min-h-screen bg-neutral-50">
      {/* Navigation */}
      <nav className="sticky top-0 z-50 bg-white border-b border-neutral-200">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex items-center justify-between h-14">
            <Link to="/" className="flex items-center gap-2">
              <Stethoscope className="w-5 h-5 text-primary-700" />
              <span className="text-sm font-semibold text-neutral-900">GREG.ai</span>
            </Link>
            <div className="flex items-center gap-4">
              <span className="text-sm text-neutral-600">
                {store.practiceName || store.physicianName || 'My Practice'}
              </span>
              <Button size="sm" variant="ghost">
                <Bell className="w-4 h-4" />
              </Button>
            </div>
          </div>
        </div>
      </nav>

      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        {/* Header */}
        <div className="mb-8">
          <h1 className="text-3xl font-bold text-neutral-900">Practice Dashboard</h1>
          <p className="text-neutral-500 mt-1">
            {store.practiceName
              ? `${store.practiceName} -- ${store.targetCity || ''}, ${store.targetState || ''}`
              : 'Track your progress across all practice areas'}
          </p>
        </div>

        {/* Overall Progress */}
        <Card className="mb-8 border-primary-200 bg-gradient-to-r from-primary-50 to-white">
          <CardContent className="py-6">
            <div className="flex items-center gap-6">
              <div className="flex-shrink-0">
                <div className="w-20 h-20 rounded-full bg-primary-100 flex items-center justify-center">
                  <TrendingUp className="w-8 h-8 text-primary-600" />
                </div>
              </div>
              <div className="flex-1">
                <div className="flex items-center justify-between mb-2">
                  <h3 className="text-lg font-semibold text-neutral-900">Overall Progress</h3>
                  <span className="text-2xl font-bold text-primary-700">{overallProgress}%</span>
                </div>
                <ProgressBar
                  value={overallProgress}
                  size="lg"
                  variant={overallProgress === 100 ? 'accent' : 'primary'}
                />
                <p className="text-sm text-neutral-500 mt-2">
                  {cards.filter((c) => c.status === 'complete').length} of {cards.length} areas
                  complete
                </p>
              </div>
            </div>
          </CardContent>
        </Card>

        <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
          {/* Main grid: area cards */}
          <div className="lg:col-span-2 space-y-4">
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              {cards.map((card) => (
                <Card
                  key={card.id}
                  className={`transition-shadow hover:card-shadow-lg ${
                    activeSection === card.id ? 'ring-2 ring-primary-300' : ''
                  }`}
                >
                  <CardHeader className="pb-2">
                    <div className="flex items-center justify-between">
                      <div className="flex items-center gap-2">
                        {card.icon}
                        <CardTitle className="text-base">{card.title}</CardTitle>
                      </div>
                      {statusBadge(card.status)}
                    </div>
                    <CardDescription className="text-xs">Agent: {card.agent}</CardDescription>
                  </CardHeader>
                  <CardContent className="py-2">
                    <ProgressBar
                      value={card.progress}
                      size="sm"
                      showPercentage
                      variant={card.progress === 100 ? 'accent' : 'primary'}
                      className="mb-3"
                    />
                    <ul className="space-y-1.5">
                      {card.tasks.map((task) => (
                        <li key={task.label} className="flex items-center gap-2 text-xs">
                          {task.done ? (
                            <CheckCircle2 className="w-3.5 h-3.5 text-emerald-500 flex-shrink-0" />
                          ) : (
                            <AlertCircle className="w-3.5 h-3.5 text-neutral-300 flex-shrink-0" />
                          )}
                          <span className={task.done ? 'text-neutral-400' : 'text-neutral-600'}>
                            {task.label}
                          </span>
                        </li>
                      ))}
                    </ul>
                  </CardContent>
                  <CardFooter className="pt-2">
                    <Link to={card.route} className="w-full">
                      <Button variant="ghost" size="sm" className="w-full justify-between">
                        View Details
                        <ArrowRight className="w-3.5 h-3.5" />
                      </Button>
                    </Link>
                  </CardFooter>
                </Card>
              ))}
            </div>
          </div>

          {/* Sidebar: Activity + Quick Actions */}
          <div className="space-y-6">
            {/* Quick Actions */}
            <Card>
              <CardHeader>
                <CardTitle className="text-base">Quick Actions</CardTitle>
              </CardHeader>
              <CardContent className="space-y-2">
                <Link to="/start" className="block">
                  <Button variant="outline" size="sm" className="w-full justify-start">
                    <ArrowRight className="w-4 h-4" />
                    Continue Onboarding
                  </Button>
                </Link>
                <Button variant="ghost" size="sm" className="w-full justify-start">
                  <DollarSign className="w-4 h-4" />
                  View Budget Report
                </Button>
                <Button variant="ghost" size="sm" className="w-full justify-start">
                  <Shield className="w-4 h-4" />
                  Check Credential Status
                </Button>
                <Button variant="ghost" size="sm" className="w-full justify-start">
                  <ShieldCheck className="w-4 h-4" />
                  Run Compliance Audit
                </Button>
              </CardContent>
            </Card>

            {/* Recent Activity */}
            <Card>
              <CardHeader>
                <CardTitle className="text-base flex items-center gap-2">
                  <Clock className="w-4 h-4 text-neutral-400" />
                  Recent Activity
                </CardTitle>
              </CardHeader>
              <CardContent>
                <ul className="space-y-3">
                  {recentActivity.map((activity, i) => (
                    <li key={i} className="flex items-start gap-3">
                      <div
                        className={`w-2 h-2 rounded-full mt-1.5 flex-shrink-0 ${
                          activity.type === 'success' ? 'bg-emerald-500' : 'bg-blue-400'
                        }`}
                      />
                      <div>
                        <p className="text-sm text-neutral-700">{activity.message}</p>
                        <p className="text-xs text-neutral-400">{activity.time}</p>
                      </div>
                    </li>
                  ))}
                </ul>
              </CardContent>
            </Card>

            {/* Practice Info */}
            {store.physicianName && (
              <Card>
                <CardHeader>
                  <CardTitle className="text-base">Practice Details</CardTitle>
                </CardHeader>
                <CardContent>
                  <dl className="space-y-2 text-sm">
                    {store.physicianName && (
                      <div>
                        <dt className="text-neutral-400 text-xs">Physician</dt>
                        <dd className="text-neutral-700 font-medium">{store.physicianName}</dd>
                      </div>
                    )}
                    {store.specialty && (
                      <div>
                        <dt className="text-neutral-400 text-xs">Specialty</dt>
                        <dd className="text-neutral-700 font-medium capitalize">
                          {store.specialty.replace(/-/g, ' ')}
                        </dd>
                      </div>
                    )}
                    {(store.targetCity || store.targetState) && (
                      <div>
                        <dt className="text-neutral-400 text-xs">Location</dt>
                        <dd className="text-neutral-700 font-medium">
                          {store.targetCity}{store.targetCity && store.targetState ? ', ' : ''}{store.targetState}
                        </dd>
                      </div>
                    )}
                    {store.practiceType && (
                      <div>
                        <dt className="text-neutral-400 text-xs">Practice Type</dt>
                        <dd className="text-neutral-700 font-medium capitalize">
                          {store.practiceType.replace(/-/g, ' ')}
                        </dd>
                      </div>
                    )}
                  </dl>
                </CardContent>
              </Card>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
