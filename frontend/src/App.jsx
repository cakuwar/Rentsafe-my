import { useEffect } from "react";
import { Navigate, Route, Routes, useLocation } from "react-router-dom";
import Navbar from "./components/Navbar.jsx";
import Footer from "./components/Footer.jsx";
import HomePage from "./pages/HomePage.jsx";
import AnalysePage from "./pages/AnalysePage.jsx";
import GuidePage from "./pages/GuidePage.jsx";
import AboutPage from "./pages/AboutPage.jsx";

// The design switches screens in memory; here each is a route so the browser's
// back button works. The Guide is a dark page with its own bar and footer.
export default function App() {
  const { pathname } = useLocation();
  const isGuide = pathname === "/guide";

  useEffect(() => {
    window.scrollTo(0, 0);
  }, [pathname]);

  return (
    <div className={isGuide ? "min-h-screen" : "min-h-screen bg-cream font-sans text-navy"}>
      {!isGuide && <Navbar />}
      <Routes>
        <Route path="/" element={<HomePage />} />
        <Route path="/analyse" element={<AnalysePage />} />
        <Route path="/guide" element={<GuidePage />} />
        <Route path="/about" element={<AboutPage />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
      {!isGuide && <Footer />}
    </div>
  );
}
