({
  // Please visit the URL below for more information:
  // https://shd101wyy.github.io/markdown-preview-enhanced/#/extend-parser

  onWillParseMarkdown: async function(markdown) {
    return markdown;
  },

  onDidParseMarkdown: async function(html) {
    let html_ = html

    html_ = html_.replace(
      /:::[nN][oO][tT][eE]([\w\W]+?):::/g, 
      (whole, content) => `
        \<p id="note"\>
        📝Note<br>
        ${content}
        \<\/p\>
      `,
    );

    html_ = html_.replace(
      /:::[tT][iI][pP]([\w\W]+?):::/g, 
      (whole, content) => `
        \<p id="tip"\>
        💡Tip<br>
        ${content}
        \<\/p\>
      `,
    );

    html_ = html_.replace(
      /:::[iI][nN][fF][oO]([\w\W]+?):::/g, 
      (whole, content) => `
        \<p id="info"\>
        🔍Info<br>
        ${content}
        \<\/p\>
      `,
    );

    html_ = html_.replace(
      /:::[wW][aA][rR][nN][iI][nN][gG]([\w\W]+?):::/g, 
      (whole, content) => `
        \<p id="warning"\>
        🔥Warning<br>
        ${content}
        \<\/p\>
      `,
    );

    html_ = html_.replace(
      /:::[cC][aA][uU][tT][iI][oO][nN]([\w\W]+?):::/g, 
      (whole, content) => `
        \<p id="caution"\>
        ⚡Caution<br>
        ${content}
        \<\/p\>
      `,
    );

    html_ = html_.replace(
      /:::[sS][aA][mM][pP][lL][eE]([\w\W]+?):::/g, 
      (whole, content) => `
        \<p id="sample"\>
        💻Sample<br>
        ${content}
        \<\/p\>
      `,
    );

    html_ = html_.replace(
      /:::[rR][eE][sS][uU][lL][tT]([\w\W]+?):::/g, 
      (whole, content) => `
        \<p id="result"\>
        🔴Result<br>
        ${content}
        \<\/p\>
      `,
    );

    return html_;
  },
})