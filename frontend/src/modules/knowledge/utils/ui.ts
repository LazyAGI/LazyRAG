class UIUtils {
  public static generatePageToken = (params: {
    page: number;
    pageSize: number;
    total: number;
  }) => {
    const { page, pageSize, total } = params;
    if (!page) {
      return "";
    }
    return btoa(
      JSON.stringify({
        Start: page * pageSize,
        Limit: pageSize,
        TotalCount: total,
      }),
    );
  };
}
export default UIUtils;
