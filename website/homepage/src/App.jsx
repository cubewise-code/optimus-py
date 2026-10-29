import Navigation from './components/Navigation'
import Hero from './components/Hero'
import WhyOrder from './components/WhyOrder'
import HowItWorks from './components/HowItWorks'
import Modes from './components/Modes'
import OptimizeDb from './components/OptimizeDb'
import V12 from './components/V12'
import WebUI from './components/WebUI'
import FeatureExplorer from './components/FeatureExplorer'
import GetStarted from './components/GetStarted'
import Footer from './components/Footer'

export default function App() {
  return (
    <div className="min-h-screen bg-canvas text-ink overflow-x-hidden">
      <Navigation />
      <main>
        <Hero />
        <V12 />
        <WebUI />
        <OptimizeDb />
        <WhyOrder />
        <HowItWorks />
        <Modes />
        <FeatureExplorer />
        <GetStarted />
      </main>
      <Footer />
    </div>
  )
}
