export const MAX_COMPARE = 4;

export const compareHref = (ids: number[]) => (ids.length ? `/compare?ids=${ids.join(",")}` : "/compare");
