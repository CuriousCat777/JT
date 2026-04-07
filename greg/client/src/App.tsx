import { BrowserRouter, Route, Routes } from 'react-router-dom';
import Assessment from '@/pages/Assessment';
import Dashboard from '@/pages/Dashboard';
import Landing from '@/pages/Landing';
import OverlordGuardian from '@/pages/OverlordGuardian';

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path='/' element={<Landing />} />
        <Route path='/start' element={<Assessment />} />
        <Route path='/dashboard' element={<Dashboard />} />
        <Route path='/dashboard/credentials' element={<Dashboard section='credentials' />} />
        <Route path='/dashboard/formation' element={<Dashboard section='formation' />} />
        <Route path='/dashboard/compliance' element={<Dashboard section='compliance' />} />
        <Route path='/dashboard/clinical' element={<Dashboard section='clinical' />} />
        <Route path='/dashboard/financial' element={<Dashboard section='financial' />} />
        <Route path='/dashboard/network' element={<Dashboard section='network' />} />
        <Route path='/overlord-guardian' element={<OverlordGuardian />} />
      </Routes>
    </BrowserRouter>
  );
}
