import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import Login from "./pages/Login";
import Layout from "./pages/Layout";
import Tasks from "./pages/Tasks";
import Products from "./pages/Products";
import ReviewBoard from "./pages/ReviewBoard";
import ListingReview from "./pages/ListingReview";
import Shops from "./pages/Shops";

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
        </Route>
        <Route path="*" element={<Navigate to="/tasks" replace />} />
      </Routes>
    </BrowserRouter>
  );
}
