import assert from "node:assert/strict";
import test from "node:test";
import { h } from "vue";
import { loadSource, mountTemplate } from "./helpers/vueHarness.mjs";

function mountLogo(animated, reduced) {
  const ChatUILogo = loadSource(
    new URL("../src/components/chat/ChatUILogo.vue", import.meta.url),
    {},
    { window: { matchMedia: () => ({ matches: reduced }) } },
    true,
  ).default;
  // Rendered from a parent so attribute fallthrough (the class) is exercised.
  return mountTemplate({
    render: () => h(ChatUILogo, { animated, class: "logo" }),
  });
}

for (const [animated, reduced, moving] of [
  [false, false, false],
  [true, true, false],
  [true, false, true],
]) {
  test(`logo: animated=${animated}, reduced motion=${reduced}`, () => {
    const logo = mountLogo(animated, reduced);
    try {
      const count = (...types) =>
        logo.findAll((node) => types.includes(node.type)).length;
      const svgs = logo.findAll((node) => node.type === "svg");
      assert.equal(svgs.length, 1);
      assert.equal(svgs[0].props.class, "logo");
      assert.equal(count("animate", "animateTransform") > 0, moving);
      // At rest it is the plain mark: no mask, no gradients.
      assert.equal(count("mask", "linearGradient") > 0, moving);
    } finally {
      logo.stop();
    }
  });
}
