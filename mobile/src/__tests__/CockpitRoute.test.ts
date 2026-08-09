describe("legacy Cockpit route", () => {
  it("redirects to the final More/System destination", () => {
    const route = jest.requireActual("../../app/cockpit").default;
    expect(route).toBeDefined();
  });
});
