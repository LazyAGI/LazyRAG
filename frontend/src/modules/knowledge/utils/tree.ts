class TreeUtils {
  public static arrayToTree = (params: {
    array: { id: string; parentId: string; [a: string]: any }[];
    parentId?: string;
    level?: number;
  }) => {
    const { array, parentId = "", level = 0 } = params;
    const tree: any[] = [];
    array.forEach((item) => {
      if (item.parentId === parentId) {
        const children = this.arrayToTree({
          array,
          parentId: item.id,
          level: level + 1,
        });
        if (children.length) {
          item.children = children;
        }
        tree.push({ ...item, level });
      }
    });
    return tree;
  };

  // 查找当前节点
  public static findNode = (
    treeList: any,
    match: (node: any) => boolean,
  ): any => {
    for (let i = 0; i < treeList.length; i++) {
      const item = treeList[i];
      if (match(item)) {
        return item;
      }

      if (item?.children) {
        const node = this.findNode(item.children, match);
        if (node) {
          return node;
        }
      }
    }

    return undefined;
  };

  /** 查找目标节点的所有祖先文件夹的 document_id（取消子项选择时需同步移除父文件夹） */
  public static findAncestorFolderIds = (
    tree: { document_id?: string; type?: string; children?: any[] }[],
    targetId: string,
    path: { document_id?: string; type?: string }[] = [],
  ): string[] => {
    for (const node of tree) {
      if (node.document_id === targetId) {
        return path
          .filter((n) => n.type === "FOLDER")
          .map((n) => n.document_id!)
          .filter(Boolean);
      }
      if (node.children?.length) {
        const found = this.findAncestorFolderIds(node.children, targetId, [
          ...path,
          node,
        ]);
        if (found.length > 0) return found;
      }
    }
    return [];
  };

  // 通过key查找所有父节点 返回结果包含当前节点
  public static findParents = (
    treeList: { key: string | number; children?: any[] }[],
    key: string,
  ): any[] => {
    for (let i = 0; i < treeList.length; i++) {
      const item = treeList[i];
      if (item.key === key) {
        return [item];
      }
      if (item.children) {
        const pathArr = this.findParents(item.children, key);
        if (pathArr.length > 0) {
          return [item, ...pathArr];
        }
      }
    }
    return [];
  };

  // 树状数组打平
  public static flattenTree = (
    treeList: { key: string | number; children?: any[] }[],
    nodeList: any[] = [],
  ): any[] => {
    treeList.forEach((node) => {
      nodeList.push(node);
      if (node.children) {
        this.flattenTree(node.children, nodeList);
      }
    });
    return nodeList;
  };
}

export default TreeUtils;
