import { useEffect, useState } from "react";
import { loadCategoryImage } from "../lib/imageCache";

/** A category's own picture, loaded with auth. Renders `fallback` if absent. */
export default function CategoryImage({
  name,
  hasImage,
  version = "0",
  fallback,
}: {
  name: string;
  hasImage: boolean;
  /** Changes when the picture is replaced, so the cache is bypassed. */
  version?: string;
  fallback: React.ReactNode;
}) {
  const [url, setUrl] = useState<string | null>(() => {
    if (!hasImage) return null;
    const r = loadCategoryImage(name, version);
    return typeof r === "string" ? r : null;
  });
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    if (!hasImage) {
      setUrl(null);
      return;
    }
    const result = loadCategoryImage(name, version);
    if (typeof result === "string") {
      setUrl(result);
      return;
    }
    let cancelled = false;
    setFailed(false);
    result
      .then((u) => !cancelled && setUrl(u))
      .catch(() => !cancelled && setFailed(true));
    return () => {
      cancelled = true;
    };
  }, [name, hasImage, version]);

  if (hasImage && url && !failed) {
    return <img src={url} alt={name} className="item-img cover" loading="lazy" />;
  }
  return <>{fallback}</>;
}
