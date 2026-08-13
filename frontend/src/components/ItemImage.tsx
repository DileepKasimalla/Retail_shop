import { useEffect, useState } from "react";
import { loadProductImage } from "../lib/imageCache";

/** Emoji shown when an item has no photo, picked from its category/name. */
const CATEGORY_ICONS: [RegExp, string][] = [
  [/grain|rice|wheat|dal|pulse|staple/i, "🌾"],
  [/dairy|milk|curd|egg|butter|cheese/i, "🥛"],
  [/veg|onion|potato|tomato/i, "🥬"],
  [/fruit/i, "🍎"],
  [/spice|masala|chilli|turmeric/i, "🌶️"],
  [/bever|tea|coffee|drink|juice/i, "☕"],
  [/bakery|bread|cake|biscuit/i, "🍞"],
  [/snack|chips|namkeen/i, "🍪"],
  [/oil|ghee/i, "🫒"],
  [/personal|soap|shampoo|tooth/i, "🧴"],
  [/house|clean|detergent|match|gas/i, "🧹"],
  [/meat|fish|chicken/i, "🍗"],
  [/grocer|general|store/i, "🛒"],
];

export function iconFor(category: string, name = ""): string {
  const hay = `${category} ${name}`;
  for (const [re, icon] of CATEGORY_ICONS) {
    if (re.test(hay)) return icon;
  }
  return "🛒";
}

/** Deterministic pastel tint so items without photos still look varied. */
function tintFor(seed: string): number {
  let h = 0;
  for (let i = 0; i < seed.length; i++) h = (h * 31 + seed.charCodeAt(i)) % 360;
  return h;
}

interface ItemImageProps {
  productId: number;
  hasImage: boolean;
  name: string;
  category: string;
  version?: string;
  className?: string;
}

export default function ItemImage({
  productId,
  hasImage,
  name,
  category,
  version = "0",
  className = "",
}: ItemImageProps) {
  // Already-cached photos resolve synchronously, so they paint on first render
  // with no flash of the placeholder.
  const [url, setUrl] = useState<string | null>(() => {
    if (!hasImage) return null;
    const r = loadProductImage(productId, version);
    return typeof r === "string" ? r : null;
  });
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    if (!hasImage) {
      setUrl(null);
      return;
    }
    const result = loadProductImage(productId, version);
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
  }, [productId, hasImage, version]);

  if (hasImage && url && !failed) {
    return <img src={url} alt={name} className={`item-img ${className}`} loading="lazy" />;
  }
  return (
    <div
      className={`item-img placeholder ${className}`}
      style={{ background: `hsl(${tintFor(category + name)} 70% 94%)` }}
      aria-label={name}
    >
      <span>{iconFor(category, name)}</span>
    </div>
  );
}
