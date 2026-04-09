import unittest

from bilibili_unreal_kb.parser import parse_search_page_with_pure_python


class ParserTests(unittest.TestCase):
    def test_parse_search_page_with_pure_python_extracts_literal_fields(self) -> None:
        html = """
<script>
window.__pinia=(function(a,b,c){return {searchResponse:{searchAllResponse:{result:[
{result_type:a,data:[{aid:123,bvid:"BV1TEST12345",title:"UE5 \\u003Cem class=\\"keyword\\"\\u003E教程\\u003C/em\\u003E",
description:"蓝图入门",author:"Test UP",play:456,duration:"12:34",tag:"UE5,蓝图",pubstr:"2026-03-24",typename:"知识",typeid:36}]}}
]}}})(null,false,[]);
</script>
"""
        results = parse_search_page_with_pure_python(html)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].bvid, "BV1TEST12345")
        self.assertEqual(results[0].aid, 123)
        self.assertEqual(results[0].title, "UE5 教程")
        self.assertEqual(results[0].author, "Test UP")
        self.assertEqual(results[0].play_count, 456)
        self.assertEqual(results[0].duration_text, "12:34")
        self.assertEqual(results[0].tag_text, "UE5,蓝图")
        self.assertEqual(results[0].publish_text, "2026-03-24")
        self.assertEqual(results[0].partition_name, "知识")
        self.assertEqual(results[0].partition_id, 36)

    def test_parse_search_page_with_pure_python_resolves_iife_bindings(self) -> None:
        html = """
<script>
window.__pinia=(function(a,b,c,d){return {searchResponse:{searchAllResponse:{result:[
{result_type:a,data:[{aid:b,bvid:"BV1TEST67890",title:"UE5 入门",description:"desc",author:c,play:789,duration:"08:00",tag:d,pubstr:c}]}}
]}}})(null,456,"placeholder","tag_placeholder");
</script>
"""
        results = parse_search_page_with_pure_python(html)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].bvid, "BV1TEST67890")
        self.assertEqual(results[0].aid, 456)
        self.assertEqual(results[0].author, "placeholder")
        self.assertEqual(results[0].publish_text, "placeholder")
        self.assertEqual(results[0].tag_text, "tag_placeholder")


if __name__ == "__main__":
    unittest.main()
