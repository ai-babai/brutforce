// Short editorial paraphrases and primary sources: design/wine-ux-v3/air35/waiting-notes.md.
export const wineNotes = [
  "Белое вино тоже можно сделать из тёмного винограда.",
  "Пузырьки шампанского рождаются при втором брожении в бутылке.",
  "Красное вино обычно получает цвет от кожицы винограда.",
  "Дубовая бочка может подарить вину аромат ванили.",
  "Оранжевому вину цвет даёт кожица белого винограда.",
  "Розовое вино получает цвет при коротком контакте с кожицей.",
  "У Сира бывает аромат чёрного перца — без добавления специй.",
  "В аромате Муската можно узнать свежий виноград.",
  "Прохладный климат помогает сохранить кислотность винограда.",
  "Созревая, виноград накапливает сахар и теряет кислотность.",
  "Брожение рождает новые ароматы, которых не было в винограде.",
  "Дуб меняет характер вина, но не гарантирует его качество.",
] as const;

export function shuffleWineNotes(random: () => number, previous?: number): number[] {
  const deck = wineNotes.map((_, index) => index);
  for (let index = deck.length - 1; index > 0; index -= 1) {
    const swap = Math.floor(random() * (index + 1));
    [deck[index], deck[swap]] = [deck[swap], deck[index]];
  }
  if (deck[0] === previous) {
    const swap = 1 + Math.floor(random() * (deck.length - 1));
    [deck[0], deck[swap]] = [deck[swap], deck[0]];
  }
  return deck;
}
