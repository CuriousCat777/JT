import { Link } from 'react-router-dom';
import {
  Shield,
  Building2,
  ShieldCheck,
  Monitor,
  DollarSign,
  Users,
  ArrowRight,
  Check,
  MapPin,
  Stethoscope,
  Zap,
  Lock,
} from 'lucide-react';
import { Button } from '@/components/ui/Button';
import { Card, CardContent } from '@/components/ui/Card';
import { Badge } from '@/components/ui/Badge';

const AGENTS = [
  {
    name: 'CREDENCE',
    tagline: 'Credentialing Intelligence',
    description:
      'Automated NPI verification, state license tracking, DEA registration, board certification, and payer credentialing across all 50 states.',
    icon: Shield,
    color: 'text-blue-600',
    bg: 'bg-blue-50',
  },
  {
    name: 'FORMA',
    tagline: 'Business Formation',
    description:
      'Entity type recommendation, state-specific registration, EIN acquisition, operating agreements, and bank account setup guidance.',
    icon: Building2,
    color: 'text-emerald-600',
    bg: 'bg-emerald-50',
  },
  {
    name: 'COMPLY',
    tagline: 'Regulatory Compliance',
    description:
      'CMS enrollment, HIPAA compliance program, OIG exclusion checks, CLIA waivers, and ongoing regulatory monitoring.',
    icon: ShieldCheck,
    color: 'text-violet-600',
    bg: 'bg-violet-50',
  },
  {
    name: 'VITALS',
    tagline: 'Clinical Setup',
    description:
      'EHR selection and configuration, FHIR interoperability, e-prescribing setup, lab connectivity, and clinical workflow design.',
    icon: Monitor,
    color: 'text-rose-600',
    bg: 'bg-rose-50',
  },
  {
    name: 'LEDGER',
    tagline: 'Financial Intelligence',
    description:
      'Startup budgeting, fee schedule generation, billing system setup, payer contract negotiation, and revenue cycle management.',
    icon: DollarSign,
    color: 'text-amber-600',
    bg: 'bg-amber-50',
  },
  {
    name: 'NEXUS',
    tagline: 'Network & Launch',
    description:
      'Provider directory optimization, referral network building, community outreach strategy, and go-live coordination.',
    icon: Users,
    color: 'text-teal-600',
    bg: 'bg-teal-50',
  },
];

const PRICING = [
  {
    name: 'Explore',
    price: 'Free',
    period: '',
    description: 'See what it takes to start your practice',
    features: [
      'Practice assessment quiz',
      'Startup cost estimator',
      'State requirements overview',
      'Community forum access',
    ],
    cta: 'Start Free',
    featured: false,
  },
  {
    name: 'Starter',
    price: '$49',
    period: '/month',
    description: 'Essential tools for solo practitioners',
    features: [
      'Everything in Explore',
      'CREDENCE credential tracking',
      'FORMA entity guidance',
      'Basic compliance checklists',
      'Email support',
    ],
    cta: 'Get Started',
    featured: false,
  },
  {
    name: 'Professional',
    price: '$149',
    period: '/month',
    description: 'Full platform for serious practice builders',
    features: [
      'Everything in Starter',
      'All 6 AI agents active',
      'FHIR bridge configuration',
      'Fee schedule generation',
      'Payer contract templates',
      'Priority support',
    ],
    cta: 'Start Professional',
    featured: true,
  },
  {
    name: 'Enterprise',
    price: '$299',
    period: '/month',
    description: 'Multi-provider groups and health systems',
    features: [
      'Everything in Professional',
      'Multi-provider management',
      'Custom integrations',
      'Dedicated account manager',
      'SLA guarantees',
      'White-label options',
    ],
    cta: 'Contact Sales',
    featured: false,
  },
];

export default function Landing() {
  return (
    <div className="min-h-screen">
      {/* Navigation */}
      <nav className="sticky top-0 z-50 bg-white/80 backdrop-blur-md border-b border-neutral-200">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex items-center justify-between h-16">
            <div className="flex items-center gap-2">
              <Stethoscope className="w-7 h-7 text-primary-700" />
              <span className="text-xl font-bold text-neutral-900">
                GREG<span className="text-primary-600">.</span>ai
              </span>
            </div>
            <div className="hidden md:flex items-center gap-8">
              <a href="#agents" className="text-sm text-neutral-600 hover:text-neutral-900 transition-colors">
                Agents
              </a>
              <a href="#case-study" className="text-sm text-neutral-600 hover:text-neutral-900 transition-colors">
                Case Study
              </a>
              <a href="#pricing" className="text-sm text-neutral-600 hover:text-neutral-900 transition-colors">
                Pricing
              </a>
              <Link to="/start">
                <Button size="sm">Start My Practice</Button>
              </Link>
            </div>
          </div>
        </div>
      </nav>

      {/* Hero */}
      <section className="relative overflow-hidden gradient-hero text-white">
        <div className="absolute inset-0 bg-[url('data:image/svg+xml,%3Csvg%20width%3D%2260%22%20height%3D%2260%22%20viewBox%3D%220%200%2060%2060%22%20xmlns%3D%22http%3A//www.w3.org/2000/svg%22%3E%3Cg%20fill%3D%22none%22%20fill-rule%3D%22evenodd%22%3E%3Cg%20fill%3D%22%23ffffff%22%20fill-opacity%3D%220.03%22%3E%3Cpath%20d%3D%22M36%2034v-4h-2v4h-4v2h4v4h2v-4h4v-2h-4zm0-30V0h-2v4h-4v2h4v4h2V6h4V4h-4zM6%2034v-4H4v4H0v2h4v4h2v-4h4v-2H6zM6%204V0H4v4H0v2h4v4h2V6h4V4H6z%22/%3E%3C/g%3E%3C/g%3E%3C/svg%3E')] opacity-50" />
        <div className="relative max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-24 lg:py-32">
          <div className="max-w-3xl">
            <Badge variant="info" className="bg-white/10 text-white border-white/20 mb-6">
              AI-Powered Practice Launch Platform
            </Badge>
            <h1 className="text-4xl lg:text-6xl font-bold leading-tight text-balance">
              Start Your Medical Practice with{' '}
              <span className="text-accent-400">AI-Powered Guidance</span>
            </h1>
            <p className="text-lg lg:text-xl text-primary-100 mt-6 max-w-2xl text-balance">
              Six specialized AI agents handle credentialing, business formation, compliance,
              clinical setup, finances, and launch -- so you can focus on patient care.
            </p>
            <div className="flex flex-col sm:flex-row gap-4 mt-10">
              <Link to="/start">
                <Button size="lg" variant="secondary" className="w-full sm:w-auto">
                  Order Your Clinic
                  <ArrowRight className="w-5 h-5" />
                </Button>
              </Link>
              <a href="#case-study">
                <Button size="lg" variant="outline" className="w-full sm:w-auto border-white/30 text-white hover:bg-white/10">
                  See Ely, MN Example
                </Button>
              </a>
            </div>
            <div className="flex items-center gap-6 mt-10 text-sm text-primary-200">
              <div className="flex items-center gap-1.5">
                <Lock className="w-4 h-4" />
                HIPAA Compliant
              </div>
              <div className="flex items-center gap-1.5">
                <Zap className="w-4 h-4" />
                Results in Days, Not Months
              </div>
              <div className="flex items-center gap-1.5">
                <Shield className="w-4 h-4" />
                SOC 2 Type II
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* Agent Grid */}
      <section id="agents" className="py-20 lg:py-28 bg-neutral-50">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="text-center max-w-2xl mx-auto mb-16">
            <h2 className="text-3xl lg:text-4xl font-bold text-neutral-900">
              Six AI Agents, One Mission
            </h2>
            <p className="text-lg text-neutral-500 mt-4">
              Each agent specializes in a critical domain of practice launch,
              working together to get you from idea to open doors.
            </p>
          </div>
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
            {AGENTS.map((agent) => (
              <Card key={agent.name} className="hover:card-shadow-lg transition-shadow duration-300">
                <CardContent className="p-6">
                  <div className={`w-12 h-12 rounded-xl ${agent.bg} flex items-center justify-center mb-4`}>
                    <agent.icon className={`w-6 h-6 ${agent.color}`} />
                  </div>
                  <h3 className="text-lg font-bold text-neutral-900">{agent.name}</h3>
                  <p className="text-sm font-medium text-primary-600 mb-2">{agent.tagline}</p>
                  <p className="text-sm text-neutral-500 leading-relaxed">{agent.description}</p>
                </CardContent>
              </Card>
            ))}
          </div>
        </div>
      </section>

      {/* Case Study: Ely, MN */}
      <section id="case-study" className="py-20 lg:py-28 bg-white">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-12 items-center">
            <div>
              <Badge variant="success" className="mb-4">Featured Scenario</Badge>
              <h2 className="text-3xl lg:text-4xl font-bold text-neutral-900">
                Dr. Chen Opens a Clinic in Ely, Minnesota
              </h2>
              <p className="text-lg text-neutral-500 mt-4">
                A mid-career family medicine physician wants to bring primary care to a
                rural community in northern Minnesota with limited healthcare access.
              </p>
              <div className="mt-8 space-y-4">
                {[
                  { label: 'Location', value: 'Ely, MN (population ~3,400)' },
                  { label: 'Specialty', value: 'Family Medicine' },
                  { label: 'Practice Type', value: 'Solo Practice (PLLC)' },
                  { label: 'Timeline', value: '6 months to open' },
                  { label: 'Budget', value: '$150,000 startup' },
                ].map((item) => (
                  <div key={item.label} className="flex items-start gap-3">
                    <div className="w-2 h-2 rounded-full bg-primary-600 mt-2 flex-shrink-0" />
                    <div>
                      <span className="text-sm font-medium text-neutral-900">{item.label}:</span>{' '}
                      <span className="text-sm text-neutral-600">{item.value}</span>
                    </div>
                  </div>
                ))}
              </div>
              <Link to="/start" className="inline-block mt-8">
                <Button size="lg">
                  <MapPin className="w-4 h-4" />
                  Try This Scenario
                </Button>
              </Link>
            </div>
            <div className="bg-neutral-50 rounded-2xl p-8 border border-neutral-200">
              <h3 className="text-lg font-semibold text-neutral-900 mb-6">
                GREG builds a complete launch plan:
              </h3>
              <div className="space-y-4">
                {[
                  { agent: 'CREDENCE', task: 'Verifies MN medical license, NPI, DEA registration' },
                  { agent: 'FORMA', task: 'Recommends PLLC in Minnesota, files with Secretary of State' },
                  { agent: 'COMPLY', task: 'CMS enrollment, HIPAA program, CLIA waiver for point-of-care tests' },
                  { agent: 'VITALS', task: 'Configures Elation EHR, Surescripts e-prescribing, Quest lab interface' },
                  { agent: 'LEDGER', task: 'Medicare fee schedule, Blue Cross MN contract, $150K budget allocation' },
                  { agent: 'NEXUS', task: 'Ely-area referral network, Boundary Waters community outreach plan' },
                ].map((step, i) => (
                  <div key={step.agent} className="flex items-start gap-3">
                    <div className="w-7 h-7 rounded-full bg-primary-100 text-primary-700 flex items-center justify-center flex-shrink-0 text-xs font-bold">
                      {i + 1}
                    </div>
                    <div>
                      <span className="text-sm font-semibold text-primary-700">{step.agent}</span>
                      <p className="text-sm text-neutral-600">{step.task}</p>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* Pricing */}
      <section id="pricing" className="py-20 lg:py-28 bg-neutral-50">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="text-center max-w-2xl mx-auto mb-16">
            <h2 className="text-3xl lg:text-4xl font-bold text-neutral-900">
              Simple, Transparent Pricing
            </h2>
            <p className="text-lg text-neutral-500 mt-4">
              Start free, scale as your practice grows. No hidden fees.
            </p>
          </div>
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
            {PRICING.map((plan) => (
              <Card
                key={plan.name}
                className={`relative ${
                  plan.featured
                    ? 'border-primary-300 ring-2 ring-primary-200 card-shadow-lg'
                    : ''
                }`}
              >
                {plan.featured && (
                  <div className="absolute -top-3 left-1/2 -translate-x-1/2">
                    <Badge variant="info" className="bg-primary-600 text-white border-primary-600">
                      Most Popular
                    </Badge>
                  </div>
                )}
                <CardContent className="p-6 flex flex-col h-full">
                  <h3 className="text-lg font-semibold text-neutral-900">{plan.name}</h3>
                  <div className="mt-2">
                    <span className="text-3xl font-bold text-neutral-900">{plan.price}</span>
                    {plan.period && (
                      <span className="text-neutral-500 text-sm">{plan.period}</span>
                    )}
                  </div>
                  <p className="text-sm text-neutral-500 mt-2">{plan.description}</p>
                  <ul className="mt-6 space-y-3 flex-1">
                    {plan.features.map((feature) => (
                      <li key={feature} className="flex items-start gap-2 text-sm text-neutral-600">
                        <Check className="w-4 h-4 text-accent-600 flex-shrink-0 mt-0.5" />
                        {feature}
                      </li>
                    ))}
                  </ul>
                  <Link to="/start" className="mt-6 block">
                    <Button
                      variant={plan.featured ? 'primary' : 'outline'}
                      className="w-full"
                    >
                      {plan.cta}
                    </Button>
                  </Link>
                </CardContent>
              </Card>
            ))}
          </div>
        </div>
      </section>

      {/* Footer */}
      <footer className="bg-neutral-900 text-neutral-400 py-12">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex flex-col md:flex-row items-center justify-between gap-4">
            <div className="flex items-center gap-2">
              <Stethoscope className="w-5 h-5 text-primary-400" />
              <span className="text-sm font-semibold text-white">GREG.ai</span>
            </div>
            <p className="text-sm">
              GREG AI Agent Platform -- Helping physicians build independent practices.
            </p>
            <p className="text-xs text-neutral-500">
              HIPAA Compliant | SOC 2 Type II | BAA Available
            </p>
          </div>
        </div>
      </footer>
    </div>
  );
}
