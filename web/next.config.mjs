/** Static export served by FastAPI under /app (same origin as the API, no CORS, one port). */
const nextConfig = {
  output: "export",
  basePath: "/app",
  trailingSlash: true,
  images: { unoptimized: true },
  reactStrictMode: true,
};
export default nextConfig;
