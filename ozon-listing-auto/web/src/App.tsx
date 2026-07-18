import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import Login from "./pages/Login";
import Layout from "./pages/Layout";
import Tasks from "./pages/Tasks";
import Products from "./pages/Products";
import ReviewBoard from "./pages/ReviewBoard";
import ListingReview from "./pages/ListingReview";
import Shops from "./pages/Shops";
import PricingSettings from "./pages/PricingSettings";
import PublishMonitor from "./pages/PublishMonitor";
import ImageStudio from "./pages/ImageStudio";
import ImagegenSettings from "./pages/settings/ImagegenSettings";
import CrawlerSettings from "./pages/settings/CrawlerSettings";
import SystemSettings from "./pages/settings/SystemSettings";

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/login" element={<Login />} />
        <Route element={<Layout />}>
          <Route path="/tasks" element={<Tasks />} />
          <Route path="/products" element={<Products />} />
          <Route path="/review" element={<ReviewBoard />} />
          <Route path="/listing" element={<ListingReview />} />
          <Route path="/shops" element={<Shops />} />
          <Route path="/pricing" element={<PricingSettings />} />
          <Route path="/monitor" element={<PublishMonitor />} />
          <Route path="/image-studio" element={<ImageStudio />} />
          <Route path="/settings/imagegen" element={<ImagegenSettings />} />
          <Route path="/settings/crawler" element={<CrawlerSettings />} />
          <Route path="/settings/system" element={<SystemSettings />} />
        </Route>
        <Route path="*" element={<Navigate to="/tasks" replace />} />
      </Routes>
    </BrowserRouter>
  );
}
