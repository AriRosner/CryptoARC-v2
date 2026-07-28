describe("temporary Cockpit route", () => {
  it("remains reachable while Portfolio owns the index tab", () => {
    expect(jest.requireActual("../../app/(tabs)/cockpit").default).toBeDefined();
  });
});
