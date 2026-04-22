const DEFAULT_IMAGE_URL =
  "https://images.unsplash.com/photo-1485965120184-e220f721d03e?auto=format&fit=crop&w=1200&q=80";
const DEFAULT_IMAGE_ALT = "A bicycle parked outdoors";
const DEFAULT_TIMEZONE = "America/Chicago";

type DailyImage = {
  dateKey: string;
  url: string;
  alt: string;
};

let dailyImageCache: DailyImage | null = null;

function getDateKey(timeZone: string) {
  const formatter = new Intl.DateTimeFormat("en-CA", {
    timeZone,
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  });

  return formatter.format(new Date());
}

export async function getDailyUnsplashBicycleImage() {
  const timeZone = process.env.PIXORDLE_TIMEZONE ?? DEFAULT_TIMEZONE;
  const dateKey = getDateKey(timeZone);

  if (dailyImageCache?.dateKey === dateKey) {
    return { imageUrl: dailyImageCache.url, imageAlt: dailyImageCache.alt };
  }

  const accessKey = process.env.UNSPLASH_ACCESS_KEY;

  if (!accessKey) {
    return { imageUrl: DEFAULT_IMAGE_URL, imageAlt: DEFAULT_IMAGE_ALT };
  }

  try {
    const response = await fetch(
      "https://api.unsplash.com/photos/random?query=bicycle&orientation=squarish",
      {
        headers: {
          Authorization: `Client-ID ${accessKey}`,
          "Accept-Version": "v1",
        },
        // Revalidate at least once per minute if this is deployed statelessly.
        next: { revalidate: 60 },
      },
    );

    if (!response.ok) {
      return { imageUrl: DEFAULT_IMAGE_URL, imageAlt: DEFAULT_IMAGE_ALT };
    }

    const data = (await response.json()) as {
      urls?: { regular?: string };
      alt_description?: string | null;
      description?: string | null;
    };

    const imageUrl = data.urls?.regular ?? DEFAULT_IMAGE_URL;
    const imageAlt = data.alt_description ?? data.description ?? DEFAULT_IMAGE_ALT;

    dailyImageCache = {
      dateKey,
      url: imageUrl,
      alt: imageAlt,
    };

    return { imageUrl, imageAlt };
  } catch {
    return { imageUrl: DEFAULT_IMAGE_URL, imageAlt: DEFAULT_IMAGE_ALT };
  }
}
